"""The dataset registry.

One entry per dataset in the release, transcribed from the Power Query
queries in `Apttus Files/*.xlsx`:

- ``mode="release"`` datasets compare the current release folder against
  the previous release folder (local comparison).
- ``mode="soql"`` datasets compare the current release (transformed to
  Salesforce loader shape) against an org export dropped into the
  ``SOQL Exports/<profile>/`` folder as ``<export_key>_<YYYY-MM-DD>.csv``.

``columns`` is the exact header row of the release files (order matters:
the M queries expand a fixed positional column list). ``drop_header_on``
lists the columns whose repeated header rows are filtered out after
concatenating the per-country files, exactly as the M code does.
``org_required``/``org_optional`` are the column lists of each workbook's
``cCRM`` query; ``org_upper`` are the columns it uppercases."""

from __future__ import annotations

from dataclasses import dataclass

from . import transforms as t

UPSERT = "upsert"
DEACTIVATE = "deactivate"
INFO = "info"  # local-comparison result reviewed/loaded manually


@dataclass(frozen=True)
class Dataset:
    key: str
    label: str
    mode: str  # "release" | "soql"
    file_contains: str
    sheet: str
    columns: tuple[str, ...]
    builder: object
    outputs: dict[str, str]
    file_excludes: tuple[str, ...] = ()
    drop_header_on: tuple[str, ...] = ()
    export_key: str | None = None
    soql_object: str | None = None
    soql_where: str | None = None
    soql_query: str | None = None  # verbatim query documented in the workbook's ReadMe
    org_required: tuple[str, ...] = ()
    org_optional: tuple[str, ...] = ("_", "Id")
    org_upper: tuple[str, ...] = ()


DATASETS: dict[str, Dataset] = {}


def _register(ds: Dataset) -> None:
    DATASETS[ds.key] = ds


_register(Dataset(
    key="G00", label="Product2", mode="soql",
    file_contains="Product2", sheet="Product2",
    columns=(
        "Product Code", "Product Name", "Commercial Product Name", "Configuration Type",
        "Type", "Product Type", "Product Business Type", "Active", "Must Configure",
        "Has Attributes", "Send to SAP", "Service Classification", "Service Cost Category",
        "Service Product Category", "Service Product Range", "RSM Type", "Language Code",
        "Language", "Short Sales Text", "Long Sales Text", "Exclude from CFD", "Validation",
        "Send Service Product Hierarchy to SAP",
    ),
    builder=t.build_g00,
    outputs={"Extra - SP": UPSERT, "Changed Products": UPSERT},
    export_key="Product2", soql_object="Product2",
    soql_where="the service-product subset your saved Product2 query selects",
    soql_query="""SELECT Id, APTS_Ext_ID__c, ProductCode, Name, Commercial_Product_Name__c, Apttus_Config2__ConfigurationType__c, APTS_Type__c, Apttus_Config2__ProductType__c, Product_Business_Type__c, IsActive,
       Apttus_Config2__Customizable__c, Apttus_Config2__HasAttributes__c, APTS_Send_to_SAP__c, APTS_Service_Classification__c, APTS_Service_Cost_Category__c,
       APTS_Service_Product_Range__c, APTS_RSM_Type__c, Description, APTS_Long_Sales_Text__c, APTS_Exclude_From_CFD__c, APTS_Send_SPH_To_SAP__c
FROM Product2
WHERE IsActive = true AND Apttus_Config2__ProductType__c = 'Service' AND (NOT ProductCode LIKE 'SVC%')""",
    org_required=(
        "APTS_Ext_ID__c", "ProductCode", "Name", "Commercial_Product_Name__c",
        "Apttus_Config2__ConfigurationType__c", "APTS_Type__c", "Apttus_Config2__ProductType__c",
        "Product_Business_Type__c", "IsActive", "Apttus_Config2__Customizable__c",
        "Apttus_Config2__HasAttributes__c", "APTS_Send_to_SAP__c",
        "APTS_Service_Classification__c", "APTS_Service_Cost_Category__c",
        "APTS_Service_Product_Range__c", "APTS_RSM_Type__c", "Description",
        "APTS_Long_Sales_Text__c", "APTS_Exclude_From_CFD__c", "APTS_Send_SPH_To_SAP__c",
    ),
    org_upper=("APTS_Exclude_From_CFD__c",),
))

_register(Dataset(
    key="G01", label="Product_Structure", mode="release",
    file_contains="Product_Structure", sheet="V_Product_Structure",
    columns=(
        "*cBOM Element", "Unique Product Code", "Product/Option Group Name", "Parent",
        "Product Option Group Min Options", "Product Option Group Max Options",
        "Product Option Group Min Total Quantity", "Product Option Group Max Total Quantity",
        "Product Option Component Min Quantity", "Product Option Component Max Quantity",
        "Product Option Component Default Quantity",
        "Product Option Component Quantity Modifiable(TRUE/FALSE)",
    ),
    builder=t.build_g01,
    outputs={
        "Extra": INFO, "Changed Models": INFO, "Changed Model Structure": INFO,
        "Changed Rows": INFO, "Changed Rows Models": INFO, "Changed Rows Model Structure": INFO,
    },
))

_register(Dataset(
    key="G02", label="CVG", mode="soql",
    file_contains="CVG", file_excludes=("Mapping", "Translation"), sheet="CVG",
    columns=("CVG Code", "CVG Description", "Exclude from CFD", "Service Group Code",
             "Service Group Description"),
    builder=t.build_g02,
    outputs={"Not Matching": UPSERT},
    export_key="CVG", soql_object="APTS_CVG__c",
    soql_query="""SELECT Name, APTS_Ext_ID__c, Description__c, APTS_Exclude_From_CFD__c, Service_Group__c, Service_Group_Description__c
FROM APTS_CVG__c""",
    org_required=("Name", "APTS_Ext_ID__c", "Description__c", "APTS_Exclude_From_CFD__c",
                  "Service_Group__c", "Service_Group_Description__c"),
    org_upper=("APTS_Exclude_From_CFD__c",),
))

_register(Dataset(
    key="G03", label="CVG_Mapping", mode="soql",
    file_contains="CVG_Mapping", sheet="CVG_Mapping",
    columns=("Product", "Product Description", "CVG Code", "Qty", "Active",
             "Check Eligibility", "Eligibility Message"),
    builder=t.build_g03,
    outputs={"Extra": UPSERT, "Extra in cCRM": DEACTIVATE},
    export_key="CVG_Mapping", soql_object="APTS_CVG_Mapping__c",
    soql_query="""SELECT APTS_Ext_ID__c, Name, APTS_Active__c, APTS_CVG__r.APTS_Ext_ID__c, APTS_CVG__r.Name, APTS_Product__r.APTS_Ext_ID__c, APTS_Product__r.Name, APTS_Quantity__c,
       APTS_Check_Eligibility__c, APTS_Eligibility_Message__c
FROM APTS_CVG_Mapping__c
WHERE APTS_Active__c = true""",
    org_required=("APTS_Ext_ID__c", "Name", "APTS_Active__c", "APTS_CVG__r.APTS_Ext_ID__c",
                  "APTS_CVG__r.Name", "APTS_Product__r.APTS_Ext_ID__c", "APTS_Product__r.Name",
                  "APTS_Quantity__c", "APTS_Check_Eligibility__c", "APTS_Eligibility_Message__c"),
    org_optional=("_", "Id", "APTS_CVG__r", "APTS_Product__r"),
    org_upper=("APTS_Check_Eligibility__c", "APTS_Active__c"),
))

_register(Dataset(
    key="G04", label="Product_Options", mode="soql",
    file_contains="Product_Options", sheet="Product_Options",
    columns=("Product", "Product Description", "Commercial System Code",
             "Commercial System Description"),
    builder=t.build_g04,
    outputs={"Extra": UPSERT},
    export_key="Product_Options", soql_object="M2O_ProductOptions__c",
    soql_query="""SELECT Name, ExternalId__c, Product__r.APTS_Ext_ID__c, Product__r.Name, Option__r.APTS_Ext_ID__c, Option__r.Name
FROM M2O_ProductOptions__c""",
    org_required=("Name", "ExternalId__c", "Option__r.APTS_Ext_ID__c", "Option__r.Name",
                  "Product__r.APTS_Ext_ID__c", "Product__r.Name"),
    org_optional=("_", "Id", "Option__r", "Product__r"),
))

_register(Dataset(
    key="G05", label="cCRM_Product_Mapping", mode="soql",
    file_contains="cCRM_Product_Mapping", sheet="cCRM_Product_Mapping",
    columns=("Name", "Apttus_ProductCode", "CCRM_ProductCode", "Service_Plan_Type__c"),
    builder=t.build_g05,
    outputs={"Not Matching": UPSERT},
    export_key="cCRM_Product_Mapping", soql_object="APTS_Apttus_cCRM_Product_Mapping__c",
    soql_query="""SELECT Apttus_Product__r.APTS_Ext_ID__c, Apttus_Product__r.Name, CCRM_Product__r.APTS_Ext_ID__c, CCRM_Product__r.Name, Service_Plan_Type__c
FROM APTS_Apttus_cCRM_Product_Mapping__c""",
    org_required=("Apttus_Product__r.APTS_Ext_ID__c", "Apttus_Product__r.Name",
                  "CCRM_Product__r.APTS_Ext_ID__c", "CCRM_Product__r.Name",
                  "Service_Plan_Type__c"),
    org_optional=("_", "Id", "Apttus_Product__r", "CCRM_Product__r"),
))

_register(Dataset(
    key="G06", label="CFD_Exhibits_Definitions", mode="soql",
    file_contains="CFD_Exhibit", sheet="CFD_Exhibits_Definitions",
    columns=("Product Code", "Product Desc", "Code", "Description", "Type"),
    builder=t.build_g06,
    outputs={"Extra": UPSERT, "Not Matching": UPSERT},
    export_key="CFD_Exhibits", soql_object="APTS_Product_Exhibit_Definition_Mapping__c",
    soql_query="""SELECT APTS_Ext_ID__c, APTS_Product_Code__c, APTS_Code__c, APTS_Description__c, APTS_Product_Description__c, APTS_Type__c, Product__r.APTS_Ext_ID__c
FROM APTS_Product_Exhibit_Definition_Mapping__c
WHERE (NOT APTS_Product_Code__c LIKE 'SVC%')""",
    org_required=("APTS_Ext_ID__c", "APTS_Product_Code__c", "APTS_Code__c",
                  "APTS_Description__c", "APTS_Product_Description__c", "APTS_Type__c",
                  "Product__r.APTS_Ext_ID__c"),
    org_optional=("_", "Id", "Product__r"),
))

_register(Dataset(
    key="G07", label="Global_EqModels", mode="soql",
    file_contains="Global_EqModels", sheet="Global_EqModels",
    columns=("Modality Code", "Equipment Code", "Equipment Description",
             "Service Product Category", "Service Product Range", "Service Product Hierarchy",
             "PM Visits per year", "PM Duration", "Grouping", "Product",
             "Available CVG Groups (rule 7)", "Not available CVG Groups (rule 5)"),
    builder=t.build_g07,
    outputs={"Not Matching": UPSERT},
    export_key="Global_EqModels", soql_object="Product2",
    soql_where="the equipment-product subset your saved Global Eq Models query selects",
    soql_query="""SELECT APTS_Ext_ID__c, ProductCode, Name, APTS_Service_Product_Category__c, APTS_Service_Product_Range__c, APTS_PM_Duration_of_visit_onsite__c, APTS_PM_Engineers_per_visit__c, APTS_PM_Visits_per_year__c, APTS_Available_CVG_Groups__c, APTS_Not_Available_CVG_Groups__c
FROM Product2
WHERE APTS_Available_CVG_Groups__c != null OR APTS_Not_Available_CVG_Groups__c != null OR APTS_Service_Product_Category__c != null OR APTS_Service_Product_Range__c != null
ORDER BY Business_Group__c, APTS_Service_Product_Category__c""",
    org_required=("APTS_Ext_ID__c", "ProductCode", "Name", "APTS_Service_Product_Category__c",
                  "APTS_Service_Product_Range__c", "APTS_PM_Duration_of_visit_onsite__c",
                  "APTS_PM_Engineers_per_visit__c", "APTS_PM_Visits_per_year__c",
                  "APTS_Available_CVG_Groups__c", "APTS_Not_Available_CVG_Groups__c"),
))

_register(Dataset(
    key="G08", label="Rule1", mode="release",
    file_contains="Rule1", sheet="Rule1_Global_System_Contract_El",
    columns=("Service Product Category (Condition)", "Service Product Range (Condition)",
             "Quote Type (Condition Criteria)", "Match in Service Assets (Condition)",
             "Match in Related Lines (Condition)", "SVC Model Code (Action)",
             "SVC Model Desc (Action)"),
    builder=t.build_g08,
    outputs={"Changed Models": INFO, "Changed Rules": INFO},
))

_register(Dataset(
    key="G09", label="Rule5", mode="release",
    file_contains="Rule5", sheet="Rule5_Global_Product_Option_Com",
    columns=("Country", "Quote Type", "Not Available CVG Groups (Condition)",
             "SVC Model Code (Condition)", "SVC Model Desc (Condition)", "Action",
             "Match in Service Assets (Condition)", "Match in Related Lines (Condition)",
             "Entitlement Code (Action)", "Action Disposition", "Message", "Key"),
    builder=t.build_g09,
    outputs={"Changed Models": INFO, "Changed Models - Rule 5": INFO},
))

_register(Dataset(
    key="G10", label="Rule7", mode="release",
    file_contains="Rule7", sheet="Rule7_Global_Equip_SP_LI_Inclus",
    columns=("Country", "Available CVG Groups (Condition)", "SVC Model Code (Condition)",
             "Entitlement Code (Condition)", "Action", "Match in Service Assets (Condition)",
             "Match in Related Lines (Condition)", "Entitlement Code (Action)", "Action Intent",
             "Action Disposition", "Message", "Key"),
    builder=t.build_g10,
    outputs={"Changed Models": INFO, "Changed Model Rules": INFO},
))

_register(Dataset(
    key="G11", label="Rule8", mode="release",
    file_contains="Rule8", sheet="Rule8_Global_MPC_StartMonthAttr",
    columns=("Product Attribute Rule", "Country", "SVC Model Code (Condition)",
             "SVC Model Desc (Condition)", "MPC Entitlement Code (Condition)",
             "Start Month Attribute Code (Action)", "Action", "Action Disposition"),
    builder=t.build_g11,
    outputs={"Changed Models": INFO, "Changed Rules": INFO},
))

_register(Dataset(
    key="L01", label="cCRM_Eq_Price_Relevant_List", mode="soql",
    file_contains="cCRM_Eq_Price_Relevant_List", sheet="tbl_Apttus_cCRM_Eq_Price_Releva",
    columns=("Country", "Equip Model", "Equip Desc"),
    drop_header_on=("Country",),
    builder=t.build_l01,
    outputs={"Extra in PST": UPSERT, "Extra in cCRM to be removed": DEACTIVATE},
    export_key="Eq_Price_Relevant_List", soql_object="Apttus_cCRM_Equipmnt_Price_Relevant_lst__c",
    soql_query="""SELECT Name, APTS_Ext_ID__c, APTS_Country__c, APTS_Product__r.APTS_Ext_ID__c, APTS_Product__r.Name
FROM Apttus_cCRM_Equipmnt_Price_Relevant_lst__c""",
    org_required=("Name", "APTS_Ext_ID__c", "APTS_Country__c",
                  "APTS_Product__r.APTS_Ext_ID__c", "APTS_Product__r.Name"),
    org_optional=("_", "Id", "APTS_Product__r"),
))

_register(Dataset(
    key="L02", label="CVG_Translation", mode="soql",
    file_contains="CVG_Translation", sheet="tbl_CVG_Translation",
    columns=("CVG Code", "CVG Description", "Country", "Country Language",
             "CVG Description Translation", "Exclude from CFD"),
    drop_header_on=("Country",),
    builder=t.build_l02,
    outputs={"Extra": UPSERT, "Not Matching": UPSERT},
    export_key="CVG_Translation", soql_object="APTS_CFD_Localization_Support__c",
    soql_where="APTS_Type__c = 'CVG'",
    soql_query="""SELECT APTS_CVG__r.APTS_Ext_ID__c, Name, APTS_Ext_Id__c, APTS_CFD_Language__c, APTS_Translated_value__c, APTS_Exclude_from_CFD__c, APTS_Type__c
FROM APTS_CFD_Localization_Support__c
WHERE APTS_Type__c = 'CVG'""",
    org_required=("APTS_CVG__r.APTS_Ext_ID__c", "Name", "APTS_Ext_ID__c",
                  "APTS_CFD_Language__c", "APTS_Translated_value__c",
                  "APTS_Exclude_from_CFD__c", "APTS_Type__c"),
    org_optional=("_", "Id", "APTS_CVG__r"),
    org_upper=("APTS_Exclude_from_CFD__c",),
))

_register(Dataset(
    key="L03", label="RSMType_Translation", mode="soql",
    file_contains="RSMType_Translation", sheet="tbl_RSMType_Translation",
    columns=("RSM Code", "RSM Consumption Type", "Country", "Country Language",
             "Global Description", "Local Description", "Local Header Sales Text"),
    drop_header_on=("Country", "Country Language"),
    builder=t.build_l03,
    outputs={"Extra": UPSERT, "Not Matching": UPSERT},
    export_key="RSM_Translation", soql_object="APTS_CFD_Localization_Support__c",
    soql_where="APTS_Type__c = 'RSM Type'",
    soql_query="""SELECT Name, APTS_Ext_Id__c, APTS_CFD_Language__c, APTS_Translated_value__c, APTS_Long_Translated_Value__c, APTS_Type__c
FROM APTS_CFD_Localization_Support__c
WHERE APTS_Type__c = 'RSM Type'""",
    org_required=("Name", "APTS_Ext_ID__c", "APTS_CFD_Language__c", "APTS_Translated_value__c",
                  "APTS_Long_Translated_Value__c", "APTS_Type__c"),
))

_register(Dataset(
    key="L04", label="ServicePlanType_Translation", mode="soql",
    file_contains="ServicePlanType", sheet="tbl_ServicePlanType_Translation",
    columns=("Service Plan Type Description", "Country", "Country Language",
             "Service Plan Type Descr Translation"),
    drop_header_on=("Country", "Service Plan Type Description"),
    builder=t.build_l04,
    outputs={"Extra": UPSERT, "Not Matching": UPSERT},
    export_key="ServicePlanType_Translation", soql_object="APTS_CFD_Localization_Support__c",
    soql_where="APTS_Type__c = 'Service Plan Type'",
    soql_query="""SELECT Name, APTS_Ext_Id__c, APTS_CFD_Language__c, APTS_Translated_value__c, APTS_Type__c
FROM APTS_CFD_Localization_Support__c
WHERE APTS_Type__c = 'Service Plan Type'""",
    org_required=("Name", "APTS_Ext_ID__c", "APTS_CFD_Language__c", "APTS_Translated_value__c",
                  "APTS_Type__c"),
))

_register(Dataset(
    key="L05", label="StartMonth_Translation", mode="soql",
    file_contains="StartMonth_Translation", sheet="tbl_StartMonth_Translation",
    columns=("Start Month Attribute Code Description", "Country", "Country Language",
             "Start Month Attr Code Descr Translation"),
    drop_header_on=("Country", "Start Month Attribute Code Description"),
    builder=t.build_l05,
    outputs={"Extra": UPSERT, "Not Matching": UPSERT},
    export_key="StartMonth_Translation", soql_object="APTS_CFD_Localization_Support__c",
    soql_where="APTS_Type__c = 'Start Month'",
    soql_query="""SELECT Name, APTS_Ext_Id__c, APTS_CFD_Language__c, APTS_Translated_value__c, APTS_Exclude_from_CFD__c, APTS_Type__c
FROM APTS_CFD_Localization_Support__c
WHERE APTS_Type__c = 'Start Month'""",
    org_required=("Name", "APTS_Ext_ID__c", "APTS_CFD_Language__c", "APTS_Translated_value__c",
                  "APTS_Exclude_from_CFD__c", "APTS_Type__c"),
    org_upper=("APTS_Exclude_from_CFD__c",),
))

_register(Dataset(
    key="L06", label="Sales_Text", mode="soql",
    file_contains="Sales_Text", sheet="tbl_Sales_Text",
    columns=("Product Code", "Product Name", "Commercial Product Name", "Country", "Language",
             "Category Desc", "Sub-Category Desc", "Short Sales Text", "Long Sales Text",
             "Exclude from CFD"),
    drop_header_on=("Country",),
    builder=t.build_l06,
    outputs={"Extra": UPSERT, "No Match": UPSERT},
    export_key="Sales_Text", soql_object="Apttus_Config2__ProductTranslation__c",
    soql_query="""SELECT APTS_Ext_ID__c, Apttus_Config2__ProductId__r.APTS_Ext_ID__c, Apttus_Config2__ProductId__r.Name, Apttus_Config2__ProductCode__c, Apttus_Config2__Name__c, APTS_Country_Code__c, APTS_Language__c, APTS_Entitlement_Category__c, APTS_Entitlement_SubCategory__c, Apttus_Config2__Description__c, APTS_Long_Sales_Text__c, APTS_Exclude_From_CFD__c
FROM Apttus_Config2__ProductTranslation__c
WHERE Apttus_Config2__ProductId__r.Apttus_Config2__ProductType__c = 'Service' AND (NOT Apttus_Config2__ProductId__r.APTS_Ext_ID__c LIKE 'SVC%')
ORDER BY APTS_Country_Code__c""",
    org_required=("Apttus_Config2__ProductId__r.APTS_Ext_ID__c",
                  "Apttus_Config2__ProductId__r.Name", "Apttus_Config2__ProductCode__c",
                  "Apttus_Config2__Name__c", "APTS_Country_Code__c", "APTS_Language__c",
                  "APTS_Entitlement_Category__c", "APTS_Entitlement_SubCategory__c",
                  "Apttus_Config2__Description__c", "APTS_Long_Sales_Text__c",
                  "APTS_Exclude_From_CFD__c", "APTS_Ext_ID__c"),
    org_optional=("_", "Id", "Apttus_Config2__ProductId__r"),
))

_register(Dataset(
    key="L07", label="Service_Price_Matrix", mode="soql",
    file_contains="Service_Price_Matrix", sheet="tbl_Service_Price_Matrix",
    columns=("Country", "CVG", "Service", "Price Type", "Monthly List Price",
             "Monthly Target Price", "Monthly Cost", "Monthly NBV", "CNA", "Currency",
             "Min Selling Term", "Max Selling Term", "Pricebook Name",
             "Pricebook Simulation Date", "Portfolio Name", "Active"),
    builder=t.build_l07,
    outputs={"Extra": UPSERT, "Not Matching": UPSERT, "Extra in cCRM (Deactivate)": DEACTIVATE},
    export_key="Service_Price_Matrix", soql_object="APTS_Service_Price_Matrix__c",
    soql_query="""SELECT APTS_Ext_ID__c, APTS_Country__c, APTS_CVG__r.APTS_Ext_ID__c, APTS_Service__r.APTS_Ext_ID__c, APTS_Service__r.Name, APTS_Price_Type__c,
       APTS_List_Price__c, APTS_Target_Price__c, APTS_Cost__c, APTS_NBV_Default_Value__c, APTS_CNA__c, CurrencyIsoCode,
       APTS_Min_Selling_Term__c, APTS_Max_Selling_Term__c, APTS_Pricebook_Name__c, APTS_Pricebook_Simulation_Date__c, APTS_Portfolio_Name__c, APTS_Active__c,
       APTS_Service_Business_Unit__c, Name
FROM APTS_Service_Price_Matrix__c
WHERE APTS_Active__c = true""",
    org_required=("APTS_Ext_ID__c", "APTS_Country__c", "APTS_CVG__r.APTS_Ext_ID__c",
                  "APTS_Service__r.APTS_Ext_ID__c", "APTS_Service__r.Name",
                  "APTS_Price_Type__c", "APTS_List_Price__c", "APTS_Target_Price__c",
                  "APTS_Cost__c", "APTS_NBV_Default_Value__c", "APTS_CNA__c", "CurrencyIsoCode",
                  "APTS_Min_Selling_Term__c", "APTS_Max_Selling_Term__c",
                  "APTS_Pricebook_Name__c", "APTS_Pricebook_Simulation_Date__c",
                  "APTS_Portfolio_Name__c", "APTS_Active__c", "APTS_Service_Business_Unit__c",
                  "Name"),
    org_optional=("_", "Id", "APTS_CVG__r", "APTS_Service__r"),
    org_upper=("APTS_Active__c",),
))

_register(Dataset(
    key="L08", label="Market_Inclusions", mode="release",
    file_contains="Market_Inclusions", sheet="tbl_Market_Inclusions",
    columns=("Option Code", "Service Model Code", "Country", "Default", "Product Range",
             "MPC Entitlement"),
    drop_header_on=("Country",),
    builder=t.build_l08,
    outputs={"Changed Models": INFO, "Changed Model Mkt Inclusion": INFO},
))

_register(Dataset(
    key="L09", label="Rule3", mode="release",
    file_contains="Rule3", sheet="tbl_Rule3_Product_Option_Compat",
    columns=("Country", "SVC Model Code (Condition)", "SVC Model Desc (Condition)",
             "Entitlement Code (Condition)", "MPC Entitlement (Condition)",
             "Match in Service Assets (Condition)", "Match in Related Lines (Condition)",
             "Action", "SVC Model Code (Action)", "SVC Model Desc (Action)",
             "Entitlement Code (Action)", "Action Intent", "Action Disposition", "Message",
             "Key"),
    drop_header_on=("Country",),
    builder=t.build_l09,
    outputs={"Changed Models": INFO, "Changed Models Rule 3": INFO},
))
