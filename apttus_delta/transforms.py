"""Per-dataset builders — line-by-line transcriptions of the M queries
embedded in the `Apttus Files/*.xlsx` workbooks.

Each builder receives the ingested all-text release frame(s) plus, for
SOQL-mode datasets, the org export frame (already schema-validated and
uppercased per the workbook's cCRM query), and returns the delta outputs
keyed by their Power Query query name — downstream consolidation reads
result sheets by exactly those names."""

from __future__ import annotations

import pandas as pd

from .delta import distinct, inner_semi, left_anti
from .normalize import (
    NULL_ONLY,
    NULL_OR_EMPTY,
    PROPAGATE,
    key_series,
    map_column,
    nbsp_trim_end,
    normalize_number,
    reformat_spm_date,
    round_sig,
    to_text,
)


def _upper(series: pd.Series) -> pd.Series:
    return map_column(series, lambda v: v.upper() if isinstance(v, str) else v)


def _replace_text(series: pd.Series, old: str, new: str) -> pd.Series:
    return map_column(series, lambda v: v.replace(old, new) if isinstance(v, str) else v)


def _round4_number(value):
    """G07 compares PM duration as a number rounded to 4 decimals on both
    sides (Number.Round, banker's rounding)."""
    if value is None:
        return None
    try:
        return to_text(round(float(str(value)), 4))
    except ValueError:
        return value


# ---------------------------------------------------------------------------
# G00. Product2  (SOQL)
# ---------------------------------------------------------------------------

_G00_ORDER = [
    "_", "APTS_Ext_ID__c", "Product_External_ID__c", "Product Code", "Product Name",
    "Commercial Product Name", "Configuration Type", "Type", "Product Type",
    "Product Business Type", "Active", "Must Configure", "Has Attributes", "Send to SAP",
    "Service Classification", "Service Cost Category", "Service Product Category",
    "Service Product Range", "RSM Type", "Language Code", "Language", "Short Sales Text",
    "Long Sales Text", "Exclude from CFD", "Validation",
    "Send Service Product Hierarchy to SAP",
]
_G00_RENAMES = {
    "Product Code": "ProductCode", "Product Name": "_Name",
    "Commercial Product Name": "Commercial_Product_Name__c",
    "Configuration Type": "Apttus_Config2__ConfigurationType__c", "Type": "APTS_Type__c",
    "Product Type": "Apttus_Config2__ProductType__c",
    "Product Business Type": "Product_Business_Type__c", "Active": "IsActive",
    "Must Configure": "Apttus_Config2__Customizable__c",
    "Has Attributes": "Apttus_Config2__HasAttributes__c", "Send to SAP": "APTS_Send_to_SAP__c",
    "Service Classification": "APTS_Service_Classification__c",
    "Service Cost Category": "APTS_Service_Cost_Category__c",
    "Service Product Range": "APTS_Service_Product_Range__c",
    "Service Product Category": "APTS_Service_Product_Category__c",
    "RSM Type": "APTS_RSM_Type__c", "Short Sales Text": "Description",
    "Long Sales Text": "APTS_Long_Sales_Text__c", "Exclude from CFD": "APTS_Exclude_From_CFD__c",
    "Send Service Product Hierarchy to SAP": "APTS_Send_SPH_To_SAP__c",
    "Validation": "_Validation", "Language Code": "_Language Code", "Language": "_Language",
}


def prep_g00(new: pd.DataFrame) -> pd.DataFrame:
    df = new.copy()
    df["APTS_Ext_ID__c"] = df["Product Code"]
    df["Product_External_ID__c"] = df["Product Code"]
    df["_"] = "[Product2]"
    df = df[_G00_ORDER].rename(columns=_G00_RENAMES)
    df["APTS_Exclude_From_CFD__c"] = _upper(df["APTS_Exclude_From_CFD__c"])
    return df


def build_g00(new, org, cfg):
    sp = prep_g00(new)
    return {
        "Extra - SP": left_anti(sp, org, ["APTS_Ext_ID__c"]),
        "Changed Products": left_anti(sp, org, ["APTS_Ext_ID__c", "APTS_Exclude_From_CFD__c"]),
    }


# ---------------------------------------------------------------------------
# G01. Product_Structure  (release vs release)
# ---------------------------------------------------------------------------

_G01_QTY_COLS = [
    "Product Option Group Min Options", "Product Option Group Max Options",
    "Product Option Group Min Total Quantity", "Product Option Group Max Total Quantity",
    "Product Option Component Min Quantity", "Product Option Component Max Quantity",
    "Product Option Component Default Quantity",
    "Product Option Component Quantity Modifiable(TRUE/FALSE)",
]


def prep_g01(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    el = df["*cBOM Element"]
    df["KMAT"] = df["Unique Product Code"].where(el == "CP", None)
    df["Option"] = df["Unique Product Code"].where(el.isin(["Option", "Attribute"]), None)
    df["UI"] = df["Product/Option Group Name"].where(el == "MS Option Class", None)
    df["Feature"] = df["Product/Option Group Name"].where(
        el.isin(["MS Nested Option Class", "MS Nested Attribute Class"]), None
    )
    for col in ("KMAT", "UI", "Feature"):
        df[col] = df[col].ffill()
    body = key_series(df, ["KMAT", "UI", "Feature", "Option"], NULL_OR_EMPTY)
    kmat = key_series(df, ["KMAT"], NULL_OR_EMPTY)
    df["Key"] = body.where(el != "CP", kmat + "_null_null_null")
    return df.drop(columns=["UI", "Feature", "Option"])


def build_g01(new_raw, old_raw, cfg):
    new, old = prep_g01(new_raw), prep_g01(old_raw)
    extra = left_anti(new, old, ["Key"])
    extra = extra[["KMAT", "*cBOM Element", "Unique Product Code", "Product/Option Group Name",
                   "Parent", *_G01_QTY_COLS, "Key"]]
    changed_models = distinct(left_anti(new, old, ["Key"]), ["KMAT"]).sort_values(
        "KMAT", kind="stable"
    )
    changed_rows = left_anti(new, old, ["Key", *_G01_QTY_COLS])
    changed_rows_models = distinct(changed_rows, ["KMAT"])
    return {
        "Extra": extra,
        "Changed Models": changed_models,
        "Changed Model Structure": inner_semi(new, changed_models, ["KMAT"]),
        "Changed Rows": changed_rows,
        "Changed Rows Models": changed_rows_models,
        "Changed Rows Model Structure": inner_semi(new, changed_rows_models, ["KMAT"]),
    }


# ---------------------------------------------------------------------------
# G02. CVG  (SOQL)
# ---------------------------------------------------------------------------

def prep_g02(new: pd.DataFrame) -> pd.DataFrame:
    df = new.rename(columns={
        "CVG Code": "Name", "CVG Description": "Description__c",
        "Exclude from CFD": "APTS_Exclude_From_CFD__c",
        "Service Group Code": "Service_Group__c",
        "Service Group Description": "Service_Group_Description__c",
    }).copy()
    df["APTS_Ext_ID__c"] = df["Name"]
    df["_"] = "[APTS_CVG__c]"
    return df[["_", "APTS_Ext_ID__c", "Name", "Description__c", "APTS_Exclude_From_CFD__c",
               "Service_Group__c", "Service_Group_Description__c"]]


def build_g02(new, org, cfg):
    sp = prep_g02(new)
    return {"Not Matching": left_anti(sp, org, ["APTS_Ext_ID__c", "Service_Group__c"])}


# ---------------------------------------------------------------------------
# G03. CVG Mapping  (SOQL)
# ---------------------------------------------------------------------------

def prep_g03(new: pd.DataFrame) -> pd.DataFrame:
    df = new.rename(columns={
        "Product": "APTS_Product__r.APTS_Ext_ID__c", "Product Description": "_APTS_Product__r.Name",
        "CVG Code": "APTS_CVG__r.APTS_Ext_ID__c", "Qty": "APTS_Quantity__c",
        "Active": "APTS_Active__c", "Check Eligibility": "APTS_Check_Eligibility__c",
        "Eligibility Message": "APTS_Eligibility_Message__c",
    }).copy()
    df["Name"] = df["_APTS_Product__r.Name"]
    df["APTS_Ext_ID__c"] = key_series(
        df, ["APTS_Product__r.APTS_Ext_ID__c", "APTS_CVG__r.APTS_Ext_ID__c"], PROPAGATE
    )
    df["_"] = "[APTS_CVG_Mapping__c]"
    return df[["_", "APTS_Ext_ID__c", "Name", "APTS_Product__r.APTS_Ext_ID__c",
               "_APTS_Product__r.Name", "APTS_CVG__r.APTS_Ext_ID__c", "APTS_Quantity__c",
               "APTS_Active__c", "APTS_Check_Eligibility__c", "APTS_Eligibility_Message__c"]]


def build_g03(new, org, cfg):
    sp = prep_g03(new)
    num = {"APTS_Quantity__c": normalize_number}
    return {
        "Extra": left_anti(sp, org, ["APTS_Ext_ID__c", "APTS_Quantity__c"], normalize=num),
        "Extra in cCRM": left_anti(org, sp, ["APTS_Ext_ID__c"]),
    }


# ---------------------------------------------------------------------------
# G04. Product_Options  (SOQL)
# ---------------------------------------------------------------------------

def prep_g04(new: pd.DataFrame) -> pd.DataFrame:
    df = new.rename(columns={
        "Product": "Product__r.APTS_Ext_ID__c", "Product Description": "Product__r.Name",
        "Commercial System Code": "Option__r.APTS_Ext_ID__c",
        "Commercial System Description": "Option__r.Name",
    }).copy()
    df["Name"] = key_series(df, ["Product__r.APTS_Ext_ID__c", "Option__r.APTS_Ext_ID__c"], PROPAGATE)
    df["ExternalId__c"] = df["Name"]
    df["_"] = "[M2O_ProductOptions__c]"
    df = df[["_", "Name", "ExternalId__c", "Product__r.APTS_Ext_ID__c", "Product__r.Name",
             "Option__r.APTS_Ext_ID__c", "Option__r.Name"]]
    return df.rename(columns={"Product__r.Name": "_Product__r.Name",
                              "Option__r.Name": "_Option__r.Name"})


def build_g04(new, org, cfg):
    return {"Extra": left_anti(prep_g04(new), org, ["ExternalId__c"])}


# ---------------------------------------------------------------------------
# G05. cCRM Product_Mapping  (SOQL)
# ---------------------------------------------------------------------------

def prep_g05(new: pd.DataFrame) -> pd.DataFrame:
    df = new.rename(columns={
        "Apttus_ProductCode": "Apttus_Product__r.APTS_Ext_ID__c",
        "CCRM_ProductCode": "CCRM_Product__r.APTS_Ext_ID__c", "Name": "_Name",
    }).copy()
    df["_"] = "[APTS_Apttus_cCRM_Product_Mapping__c]"
    return df[["_", "Apttus_Product__r.APTS_Ext_ID__c", "CCRM_Product__r.APTS_Ext_ID__c",
               "Service_Plan_Type__c", "_Name"]]


def build_g05(new, org, cfg):
    org = org.copy()
    org["Key"] = key_series(
        org,
        ["Apttus_Product__r.APTS_Ext_ID__c", "Service_Plan_Type__c",
         "CCRM_Product__r.APTS_Ext_ID__c"],
        PROPAGATE,
    )
    return {"Not Matching": left_anti(prep_g05(new), org, ["_Name"], right_on=["Key"])}


# ---------------------------------------------------------------------------
# G06. CFD_Exhibits_Definitions  (SOQL)
# ---------------------------------------------------------------------------

def prep_g06(new: pd.DataFrame) -> pd.DataFrame:
    df = new.rename(columns={
        "Product Code": "APTS_Product_Code__c", "Product Desc": "APTS_Product_Description__c",
        "Code": "APTS_Code__c", "Description": "APTS_Description__c", "Type": "APTS_Type__c",
    }).copy()
    df["Product__r.APTS_Ext_ID__c"] = df["APTS_Product_Code__c"]
    df["APTS_Ext_ID__c"] = key_series(
        df, ["APTS_Product_Code__c", "APTS_Product_Description__c", "APTS_Code__c"], PROPAGATE
    )
    df["_"] = "[APTS_Product_Exhibit_Definition_Mapping__c]"
    return df[["_", "APTS_Ext_ID__c", "APTS_Product_Code__c", "APTS_Product_Description__c",
               "APTS_Code__c", "APTS_Description__c", "APTS_Type__c", "Product__r.APTS_Ext_ID__c"]]


def build_g06(new, org, cfg):
    sp = prep_g06(new)
    return {
        "Extra": left_anti(sp, org, ["APTS_Ext_ID__c"]),
        "Not Matching": left_anti(sp, org, [
            "APTS_Ext_ID__c", "APTS_Product_Code__c", "APTS_Product_Description__c",
            "APTS_Description__c", "Product__r.APTS_Ext_ID__c",
        ]),
    }


# ---------------------------------------------------------------------------
# G07. Global Eq Models  (SOQL)
# ---------------------------------------------------------------------------

def prep_g07(new: pd.DataFrame) -> pd.DataFrame:
    df = new.rename(columns={
        "Equipment Code": "_ProductCode", "Equipment Description": "_Name",
        "Service Product Category": "APTS_Service_Product_Category__c",
        "Service Product Range": "APTS_Service_Product_Range__c",
        "PM Visits per year": "APTS_PM_Visits_per_year__c",
        "PM Duration": "APTS_PM_Duration_of_visit_onsite__c",
        "Available CVG Groups (rule 7)": "APTS_Available_CVG_Groups__c",
        "Not available CVG Groups (rule 5)": "APTS_Not_Available_CVG_Groups__c",
    }).copy()
    for col in ("APTS_Available_CVG_Groups__c", "APTS_Not_Available_CVG_Groups__c"):
        df[col] = _replace_text(df[col], ",", ";")
    df = df.drop(columns=["Modality Code", "Service Product Hierarchy", "Grouping", "Product"])
    df["APTS_Ext_ID__c"] = df["_ProductCode"]
    df["_"] = "[Product2]"
    return df[["_", "APTS_Ext_ID__c", "_ProductCode", "_Name",
               "APTS_Service_Product_Category__c", "APTS_Service_Product_Range__c",
               "APTS_PM_Visits_per_year__c", "APTS_PM_Duration_of_visit_onsite__c",
               "APTS_Available_CVG_Groups__c", "APTS_Not_Available_CVG_Groups__c"]]


def build_g07(new, org, cfg):
    sp = prep_g07(new)
    num = {"APTS_PM_Visits_per_year__c": normalize_number,
           "APTS_PM_Duration_of_visit_onsite__c": _round4_number}
    return {"Not Matching": left_anti(sp, org, [
        "APTS_Ext_ID__c", "APTS_Service_Product_Category__c", "APTS_Service_Product_Range__c",
        "APTS_PM_Visits_per_year__c", "APTS_PM_Duration_of_visit_onsite__c",
        "APTS_Available_CVG_Groups__c", "APTS_Not_Available_CVG_Groups__c",
    ], normalize=num)}


# ---------------------------------------------------------------------------
# G08. Rule 1  (release vs release)
# ---------------------------------------------------------------------------

_G08_KEY_COLS = [
    "Service Product Category (Condition)", "Service Product Range (Condition)",
    "Quote Type (Condition Criteria)", "Match in Service Assets (Condition)",
    "Match in Related Lines (Condition)", "SVC Model Code (Action)",
]


def build_g08(new_raw, old_raw, cfg):
    new, old = new_raw.copy(), old_raw.copy()
    new["Key"] = key_series(new, _G08_KEY_COLS, NULL_ONLY)
    old["Key"] = key_series(old, _G08_KEY_COLS, NULL_ONLY)
    changed = left_anti(new, old, ["Key"])
    return {
        "Changed Models": distinct(changed, ["SVC Model Code (Action)", "SVC Model Desc (Action)"],
                                   rename={"SVC Model Code (Action)": "Changed Models",
                                           "SVC Model Desc (Action)": "Model Name"}),
        "Changed Rules": changed.sort_values("SVC Model Code (Action)", kind="stable"),
    }


# ---------------------------------------------------------------------------
# G09. Rule 5  (release vs release)
# ---------------------------------------------------------------------------

_G09_KEY_COLS = ["SVC Model Code (Condition)", "Action", "Entitlement Code (Action)",
                 "Not Available CVG Groups (Condition)", "Quote Type"]


def _prep_g09(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.sort_values("SVC Model Code (Condition)", kind="stable").reset_index(drop=True)
    df["Check_Key"] = key_series(df, _G09_KEY_COLS, NULL_ONLY)
    return df


def build_g09(new_raw, old_raw, cfg):
    new, old = _prep_g09(new_raw), _prep_g09(old_raw)
    changed = left_anti(new, old, ["Check_Key"])
    models = distinct(changed, ["SVC Model Code (Condition)", "SVC Model Desc (Condition)"])
    return {
        "Changed Models": models,
        "Changed Models - Rule 5": inner_semi(new, models, ["SVC Model Code (Condition)"]),
    }


# ---------------------------------------------------------------------------
# G10. Rule 7  (release vs release; uses the file's own Key column)
# ---------------------------------------------------------------------------

_G10_ORDER = ["Country", "Available CVG Groups (Condition)", "SVC Model Code (Condition)",
              "Entitlement Code (Condition)", "Action", "Match in Service Assets (Condition)",
              "Match in Related Lines (Condition)", "Entitlement Code (Action)", "Action Intent",
              "Action Disposition", "Key", "Message"]


def build_g10(new_raw, old_raw, cfg):
    new, old = new_raw[_G10_ORDER].copy(), old_raw[_G10_ORDER].copy()
    changed = left_anti(new, old, ["Key"])
    models = distinct(changed, ["SVC Model Code (Condition)"],
                      rename={"SVC Model Code (Condition)": "Changed Models"})
    return {
        "Changed Models": models,
        "Changed Model Rules": inner_semi(new, models, ["SVC Model Code (Condition)"],
                                          right_on=["Changed Models"]),
    }


# ---------------------------------------------------------------------------
# G11. Rule 8  (release vs release)
# ---------------------------------------------------------------------------

def build_g11(new_raw, old_raw, cfg):
    new, old = new_raw.copy(), old_raw.copy()
    key_cols = ["SVC Model Code (Condition)", "MPC Entitlement Code (Condition)",
                "Start Month Attribute Code (Action)"]
    new["Key"] = key_series(new, key_cols, PROPAGATE)
    old["Key"] = key_series(old, key_cols, PROPAGATE)
    changed = left_anti(new, old, ["Key"])
    models = distinct(changed, ["SVC Model Code (Condition)", "SVC Model Desc (Condition)"])
    return {
        "Changed Models": models,
        "Changed Rules": inner_semi(new, models, ["SVC Model Code (Condition)"]),
    }


# ---------------------------------------------------------------------------
# L01. cCRM Equip Price Relevant List  (SOQL)
# ---------------------------------------------------------------------------

def prep_l01(new: pd.DataFrame) -> pd.DataFrame:
    df = new.rename(columns={
        "Equip Model": "APTS_Product__r.APTS_Ext_ID__c", "Equip Desc": "_APTS_Product__r.Name",
        "Country": "APTS_Country__c",
    }).copy()
    df["_"] = "[Apttus_cCRM_Equipmnt_Price_Relevant_lst__c]"
    df["Name"] = key_series(df, ["APTS_Product__r.APTS_Ext_ID__c", "APTS_Country__c"], PROPAGATE)
    df["APTS_Ext_ID__c"] = df["Name"]
    return df[["_", "Name", "APTS_Ext_ID__c", "APTS_Country__c",
               "APTS_Product__r.APTS_Ext_ID__c", "_APTS_Product__r.Name"]]


def build_l01(new, org, cfg):
    sp = prep_l01(new)
    return {
        "Extra in PST": left_anti(sp, org, ["APTS_Ext_ID__c"]),
        "Extra in cCRM to be removed": left_anti(org, sp, ["APTS_Ext_ID__c"]),
    }


# ---------------------------------------------------------------------------
# L02–L05. CFD localization translations  (SOQL)
# ---------------------------------------------------------------------------

_CFD_ORDER = ["_", "Name", "APTS_Ext_Id__c", "APTS_CVG__r.APTS_Ext_ID__c",
              "_APTS_CVG__r.Description__c", "APTS_CFD_Language__c", "APTS_Translated_value__c",
              "APTS_Long_Translated_Value__c", "APTS_Exclude_from_CFD__c", "APTS_Type__c"]


def prep_l02(new: pd.DataFrame) -> pd.DataFrame:
    df = new.drop(columns=["Country"]).copy()
    df["_"] = "[APTS_CFD_Localization_Support__c]"
    df["Name"] = df["CVG Code"]
    df["APTS_Ext_Id__c"] = key_series(df, ["CVG Code", "Country Language"], PROPAGATE)
    df = df.rename(columns={
        "CVG Code": "APTS_CVG__r.APTS_Ext_ID__c",
        "CVG Description": "_APTS_CVG__r.Description__c",
        "Country Language": "APTS_CFD_Language__c",
        "CVG Description Translation": "APTS_Translated_value__c",
        "Exclude from CFD": "APTS_Exclude_from_CFD__c",
    })
    df["APTS_Translated_value__c"] = map_column(df["APTS_Translated_value__c"], nbsp_trim_end)
    df["APTS_Type__c"] = "CVG"
    df["APTS_Exclude_from_CFD__c"] = _upper(df["APTS_Exclude_from_CFD__c"])
    df["APTS_Long_Translated_Value__c"] = ""
    return df[_CFD_ORDER]


def build_l02(new, org, cfg):
    sp = prep_l02(new)
    return {
        "Extra": left_anti(sp, org, ["APTS_Ext_Id__c"], right_on=["APTS_Ext_ID__c"]),
        "Not Matching": left_anti(
            sp, org,
            ["APTS_Ext_Id__c", "APTS_Translated_value__c", "APTS_Exclude_from_CFD__c"],
            right_on=["APTS_Ext_ID__c", "APTS_Translated_value__c", "APTS_Exclude_from_CFD__c"],
        ),
    }


def prep_l03(new: pd.DataFrame) -> pd.DataFrame:
    df = new.drop(columns=["RSM Code", "Country"]).copy()
    df["Name"] = key_series(df, ["Global Description", "RSM Consumption Type"], PROPAGATE,
                            sep=" - ")
    df["APTS_Ext_Id__c"] = key_series(
        df, ["Global Description", "RSM Consumption Type", "Country Language"], PROPAGATE,
        sep=" - ")
    df["_"] = "[APTS_CFD_Localization_Support__c]"
    df["APTS_Type__c"] = "RSM Type"
    df["APTS_CVG__r.APTS_Ext_ID__c"] = ""
    df["_APTS_CVG__r.Description__c"] = ""
    df = df.drop(columns=["RSM Consumption Type", "Global Description"])
    df = df.rename(columns={
        "Country Language": "APTS_CFD_Language__c",
        "Local Description": "APTS_Translated_value__c",
        "Local Header Sales Text": "APTS_Long_Translated_Value__c",
    })
    df["APTS_Translated_value__c"] = map_column(df["APTS_Translated_value__c"], nbsp_trim_end)
    df["APTS_Long_Translated_Value__c"] = map_column(df["APTS_Long_Translated_Value__c"], nbsp_trim_end)
    df["APTS_Exclude_from_CFD__c"] = "TRUE"
    return df[_CFD_ORDER]


def build_l03(new, org, cfg):
    sp = prep_l03(new)
    return {
        "Extra": left_anti(sp, org, ["APTS_Ext_Id__c"], right_on=["APTS_Ext_ID__c"]),
        "Not Matching": left_anti(
            sp, org,
            ["APTS_Ext_Id__c", "APTS_Translated_value__c", "APTS_Long_Translated_Value__c"],
            right_on=["APTS_Ext_ID__c", "APTS_Translated_value__c",
                      "APTS_Long_Translated_Value__c"],
        ),
    }


def _prep_simple_translation(new, desc_col, translation_col, type_label):
    df = new.rename(columns={desc_col: "Name", "Country Language": "APTS_CFD_Language__c",
                             translation_col: "APTS_Translated_value__c"}).copy()
    df["APTS_Translated_value__c"] = map_column(df["APTS_Translated_value__c"], nbsp_trim_end)
    df = df.drop(columns=["Country"])
    df["APTS_Ext_Id__c"] = key_series(df, ["Name", "APTS_CFD_Language__c"], PROPAGATE)
    df["_"] = "[APTS_CFD_Localization_Support__c]"
    df["APTS_Type__c"] = type_label
    df["APTS_CVG__r.APTS_Ext_ID__c"] = ""
    df["_APTS_CVG__r.Description__c"] = ""
    df["APTS_Long_Translated_Value__c"] = ""
    df["APTS_Exclude_from_CFD__c"] = "TRUE"
    return df[_CFD_ORDER]


def build_l04(new, org, cfg):
    sp = _prep_simple_translation(new, "Service Plan Type Description",
                                  "Service Plan Type Descr Translation", "Service Plan Type")
    return {
        "Extra": left_anti(sp, org, ["APTS_Ext_Id__c"], right_on=["APTS_Ext_ID__c"]),
        "Not Matching": left_anti(
            sp, org, ["APTS_Ext_Id__c", "APTS_Translated_value__c"],
            right_on=["APTS_Ext_ID__c", "APTS_Translated_value__c"],
        ),
    }


def build_l05(new, org, cfg):
    sp = _prep_simple_translation(new, "Start Month Attribute Code Description",
                                  "Start Month Attr Code Descr Translation", "Start Month")
    return {
        "Extra": left_anti(sp, org, ["APTS_Ext_Id__c"], right_on=["APTS_Ext_ID__c"]),
        "Not Matching": left_anti(
            sp, org,
            ["APTS_Ext_Id__c", "APTS_Translated_value__c", "APTS_Exclude_from_CFD__c"],
            right_on=["APTS_Ext_ID__c", "APTS_Translated_value__c", "APTS_Exclude_from_CFD__c"],
        ),
    }


# ---------------------------------------------------------------------------
# L06. Sales Text  (SOQL)
# ---------------------------------------------------------------------------

def prep_l06(new: pd.DataFrame) -> pd.DataFrame:
    df = new.rename(columns={
        "Product Code": "Apttus_Config2__ProductCode__c",
        "Product Name": "Apttus_Config2__ProductId__r.Name",
        "Commercial Product Name": "Apttus_Config2__Name__c", "Country": "APTS_Country_Code__c",
        "Language": "APTS_Language__c", "Category Desc": "APTS_Entitlement_Category__c",
        "Sub-Category Desc": "APTS_Entitlement_SubCategory__c",
        "Short Sales Text": "Apttus_Config2__Description__c",
        "Long Sales Text": "APTS_Long_Sales_Text__c", "Exclude from CFD": "APTS_Exclude_From_CFD__c",
    }).copy()
    df["Apttus_Config2__Description__c"] = map_column(df["Apttus_Config2__Description__c"], nbsp_trim_end)
    df["APTS_Long_Sales_Text__c"] = map_column(df["APTS_Long_Sales_Text__c"], nbsp_trim_end)
    df["APTS_Language__c"] = _upper(df["APTS_Language__c"])
    df["_"] = "[Apttus_Config2__ProductTranslation__c]"
    df["APTS_Ext_ID__c"] = key_series(
        df, ["Apttus_Config2__ProductCode__c", "APTS_Country_Code__c", "APTS_Language__c"],
        PROPAGATE)
    df["Apttus_Config2__ProductId__r.APTS_Ext_ID__c"] = df["Apttus_Config2__ProductCode__c"]
    df = df[["_", "APTS_Ext_ID__c", "Apttus_Config2__ProductId__r.APTS_Ext_ID__c",
             "Apttus_Config2__ProductId__r.Name", "Apttus_Config2__ProductCode__c",
             "Apttus_Config2__Name__c", "APTS_Country_Code__c", "APTS_Language__c",
             "APTS_Entitlement_Category__c", "APTS_Entitlement_SubCategory__c",
             "Apttus_Config2__Description__c", "APTS_Long_Sales_Text__c",
             "APTS_Exclude_From_CFD__c"]]
    df["APTS_Exclude_From_CFD__c"] = _replace_text(df["APTS_Exclude_From_CFD__c"], "false", "FALSE")
    df["APTS_Exclude_From_CFD__c"] = _replace_text(df["APTS_Exclude_From_CFD__c"], "true", "TRUE")
    return df.rename(columns={
        "Apttus_Config2__ProductId__r.Name": "_Apttus_Config2__ProductId__r.Name"})


def build_l06(new, org, cfg):
    sp = prep_l06(new)
    on = ["APTS_Ext_ID__c", "Apttus_Config2__Name__c", "APTS_Entitlement_Category__c",
          "APTS_Entitlement_SubCategory__c", "Apttus_Config2__Description__c",
          "APTS_Long_Sales_Text__c"]
    return {
        "Extra": left_anti(sp, org, ["APTS_Ext_ID__c"]),
        "No Match": left_anti(sp, org, on),
    }


# ---------------------------------------------------------------------------
# L07. Service Price Matrix  (SOQL; iTest4 profile adds 15-sig-digit rounding)
# ---------------------------------------------------------------------------

_L07_PRICE_COLS = ["APTS_List_Price__c", "APTS_Target_Price__c", "APTS_Cost__c",
                   "APTS_NBV_Default_Value__c"]


def _round_sig_text(value):
    if value is None:
        return None
    try:
        x = float(str(value))
    except ValueError:
        return value
    return to_text(round_sig(x, 15))


def prep_l07(new: pd.DataFrame, org_profile: str) -> pd.DataFrame:
    df = new[new["Price Type"] == "Recurring"].copy()
    df = df.rename(columns={
        "Country": "APTS_Country__c", "CVG": "APTS_CVG__r.APTS_Ext_ID__c",
        "Service": "APTS_Service__r.APTS_Ext_ID__c", "Price Type": "APTS_Price_Type__c",
        "Monthly List Price": "APTS_List_Price__c", "Monthly Target Price": "APTS_Target_Price__c",
        "Monthly Cost": "APTS_Cost__c", "Monthly NBV": "APTS_NBV_Default_Value__c",
        "CNA": "APTS_CNA__c", "Currency": "CurrencyIsoCode",
        "Min Selling Term": "APTS_Min_Selling_Term__c", "Max Selling Term": "APTS_Max_Selling_Term__c",
        "Pricebook Name": "APTS_Pricebook_Name__c",
        "Pricebook Simulation Date": "APTS_Pricebook_Simulation_Date__c",
        "Portfolio Name": "APTS_Portfolio_Name__c", "Active": "APTS_Active__c",
    })
    df["_"] = "[APTS_Service_Price_Matrix__c]"

    def ext_id(row):
        svc, cvg, country = (row["APTS_Service__r.APTS_Ext_ID__c"],
                             row["APTS_CVG__r.APTS_Ext_ID__c"], row["APTS_Country__c"])
        if country is None:  # plain `&` with null propagates null in M
            return None
        svc = "null" if svc is None or svc == "" else svc
        cvg = "null" if cvg is None or cvg == "" else cvg
        return f"{svc}_{cvg}_{country}"

    df["APTS_Ext_ID__c"] = df.apply(ext_id, axis=1) if len(df) else pd.Series([], dtype=object)
    df = df[["_", "APTS_Ext_ID__c", "APTS_Country__c", "APTS_CVG__r.APTS_Ext_ID__c",
             "APTS_Service__r.APTS_Ext_ID__c", "APTS_Price_Type__c", "APTS_List_Price__c",
             "APTS_Target_Price__c", "APTS_Cost__c", "APTS_NBV_Default_Value__c", "APTS_CNA__c",
             "CurrencyIsoCode", "APTS_Min_Selling_Term__c", "APTS_Max_Selling_Term__c",
             "APTS_Pricebook_Name__c", "APTS_Pricebook_Simulation_Date__c",
             "APTS_Portfolio_Name__c", "APTS_Active__c"]]
    df["APTS_Active__c"] = _upper(df["APTS_Active__c"])
    df["APTS_Pricebook_Simulation_Date__c"] = map_column(
        df["APTS_Pricebook_Simulation_Date__c"], reformat_spm_date)
    if org_profile == "itest4":
        for col in _L07_PRICE_COLS:
            df[col] = map_column(df[col], _round_sig_text)
    return df.reset_index(drop=True)


def build_l07(new, org, cfg):
    sp = prep_l07(new, cfg.org_profile)
    compare = ["APTS_Ext_ID__c", "APTS_List_Price__c", "APTS_Target_Price__c", "APTS_Cost__c",
               "APTS_NBV_Default_Value__c", "APTS_Min_Selling_Term__c", "APTS_Max_Selling_Term__c"]
    num = {c: normalize_number for c in compare[1:]}
    deactivate = left_anti(org, sp, ["APTS_Ext_ID__c"])
    deactivate = deactivate[["_", "APTS_Ext_ID__c", "APTS_Active__c"]].copy()
    deactivate["APTS_Active__c"] = _replace_text(deactivate["APTS_Active__c"], "TRUE", "FALSE")
    return {
        "Extra": left_anti(sp, org, ["APTS_Ext_ID__c"]),
        "Not Matching": left_anti(sp, org, compare, normalize=num),
        "Extra in cCRM (Deactivate)": deactivate,
    }


# ---------------------------------------------------------------------------
# L08. Market Inclusions  (release vs release)
# ---------------------------------------------------------------------------

def build_l08(new_raw, old_raw, cfg):
    new, old = new_raw.copy(), old_raw.copy()
    key_cols = ["Option Code", "Service Model Code", "Country", "Default", "Product Range",
                "MPC Entitlement"]
    new["Key"] = key_series(new, key_cols, PROPAGATE)
    old["Key"] = key_series(old, key_cols, PROPAGATE)
    changed = left_anti(new, old, ["Key"])
    models = distinct(changed, ["Service Model Code"])
    joined = inner_semi(new, models, ["Service Model Code"]).drop(columns=["Key"])
    return {"Changed Models": models, "Changed Model Mkt Inclusion": joined}


# ---------------------------------------------------------------------------
# L09. Rule 3  (release vs release)
# ---------------------------------------------------------------------------

_L09_KEY_COLS = ["Country", "SVC Model Code (Condition)", "Entitlement Code (Condition)",
                 "Action", "Entitlement Code (Action)", "Action Intent"]


def build_l09(new_raw, old_raw, cfg):
    new, old = new_raw.copy(), old_raw.copy()
    new["Check Key"] = key_series(new, _L09_KEY_COLS, NULL_OR_EMPTY)
    old["Check Key"] = key_series(old, _L09_KEY_COLS, NULL_OR_EMPTY)
    changed = left_anti(new, old, ["Check Key"])
    models = distinct(changed, ["SVC Model Code (Condition)"]).sort_values(
        "SVC Model Code (Condition)", kind="stable")
    joined = inner_semi(new, models, ["SVC Model Code (Condition)"]).drop(
        columns=["Key", "Check Key"])
    return {"Changed Models": models, "Changed Models Rule 3": joined}
