import pandas as pd

from apttus_delta.config import Config
from apttus_delta.transforms import build_g01, build_l07, build_l09, prep_g01, prep_l07


def _df(rows, cols):
    return pd.DataFrame(rows, columns=cols, dtype=object)


RULE3_COLS = ["Country", "SVC Model Code (Condition)", "SVC Model Desc (Condition)",
              "Entitlement Code (Condition)", "MPC Entitlement (Condition)",
              "Match in Service Assets (Condition)", "Match in Related Lines (Condition)",
              "Action", "SVC Model Code (Action)", "SVC Model Desc (Action)",
              "Entitlement Code (Action)", "Action Intent", "Action Disposition", "Message",
              "Key"]


def _rule3_row(country, model, ent_c, action, ent_a, intent):
    return [country, model, "desc", ent_c, "mpc", "FALSE", "TRUE", action, None, None,
            ent_a, intent, "disp", "msg", "k"]


def test_l09_changed_models_and_join_back():
    new = _df([
        _rule3_row("DE", "CS_1", "E1", "Include", "A1", "Auto"),
        _rule3_row("DE", "CS_1", "E2", "Include", "A2", "Auto"),   # changed row
        _rule3_row("DE", "CS_2", "E3", "Exclude", "A3", "Manual"),
    ], RULE3_COLS)
    old = _df([
        _rule3_row("DE", "CS_1", "E1", "Include", "A1", "Auto"),
        _rule3_row("DE", "CS_2", "E3", "Exclude", "A3", "Manual"),
    ], RULE3_COLS)
    out = build_l09(new, old, Config())
    assert list(out["Changed Models"]["SVC Model Code (Condition)"]) == ["CS_1"]
    # ALL rows of the changed model come back, not only the changed row
    joined = out["Changed Models Rule 3"]
    assert len(joined) == 2
    assert set(joined["Entitlement Code (Condition)"]) == {"E1", "E2"}
    assert "Key" not in joined.columns and "Check Key" not in joined.columns


def test_l09_null_and_empty_fold_into_null_token():
    a = _rule3_row("DE", "CS_1", None, "Include", "A1", "Auto")
    b = _rule3_row("DE", "CS_1", "", "Include", "A1", "Auto")
    out = build_l09(_df([a], RULE3_COLS), _df([b], RULE3_COLS), Config())
    assert len(out["Changed Models"]) == 0  # null and "" build the same check key


PS_COLS = ["*cBOM Element", "Unique Product Code", "Product/Option Group Name", "Parent",
           "Product Option Group Min Options", "Product Option Group Max Options",
           "Product Option Group Min Total Quantity", "Product Option Group Max Total Quantity",
           "Product Option Component Min Quantity", "Product Option Component Max Quantity",
           "Product Option Component Default Quantity",
           "Product Option Component Quantity Modifiable(TRUE/FALSE)"]


def _ps(el, code, group, parent):
    return [el, code, group, parent, "0", "9999", "0", "0", "0", "1", "0", "TRUE"]


def test_g01_fill_down_and_key():
    df = _df([
        _ps("CP", "CS_1", "MR Warranty", None),
        _ps("MS Option Class", None, "Contract Selection", "MR Warranty"),
        _ps("Option", "OPT_1", "Contract Selection", None),
        _ps("CP", "CS_2", "CT Warranty", None),
        _ps("Option", "OPT_2", "X", None),
    ], PS_COLS)
    prepped = prep_g01(df)
    assert list(prepped["Key"]) == [
        "CS_1_null_null_null",
        "CS_1_Contract Selection_null_null",
        "CS_1_Contract Selection_null_OPT_1",
        "CS_2_null_null_null",
        # UI filled down from the previous model — faithful to the M FillDown
        "CS_2_Contract Selection_null_OPT_2",
    ]


def test_g01_quantity_change_hits_changed_rows_not_extra():
    base = [_ps("CP", "CS_1", "G", None), _ps("Option", "OPT_1", "G", None)]
    new = _df(base, PS_COLS)
    old = _df([row[:] for row in base], PS_COLS)
    old.loc[1, "Product Option Component Max Quantity"] = "99"  # qty differs
    out = build_g01(new, old, Config())
    assert len(out["Extra"]) == 0                # same keys
    assert len(out["Changed Rows"]) == 1         # qty column diff detected
    assert list(out["Changed Rows Models"]["KMAT"]) == ["CS_1"]
    assert len(out["Changed Rows Model Structure"]) == 2  # full model joined back


SPM_COLS = ["Country", "CVG", "Service", "Price Type", "Monthly List Price",
            "Monthly Target Price", "Monthly Cost", "Monthly NBV", "CNA", "Currency",
            "Min Selling Term", "Max Selling Term", "Pricebook Name",
            "Pricebook Simulation Date", "Portfolio Name", "Active"]


def _spm(country, cvg, svc, ptype, price):
    return [country, cvg, svc, ptype, price, "10", "5", "0", "FALSE", "EUR", "12", "60",
            "PB", "09-03-2026 12:00:00 AM", "PF", "true"]


ORG_COLS = ["_", "APTS_Ext_ID__c", "APTS_Country__c", "APTS_CVG__r.APTS_Ext_ID__c",
            "APTS_Service__r.APTS_Ext_ID__c", "APTS_Service__r.Name", "APTS_Price_Type__c",
            "APTS_List_Price__c", "APTS_Target_Price__c", "APTS_Cost__c",
            "APTS_NBV_Default_Value__c", "APTS_CNA__c", "CurrencyIsoCode",
            "APTS_Min_Selling_Term__c", "APTS_Max_Selling_Term__c", "APTS_Pricebook_Name__c",
            "APTS_Pricebook_Simulation_Date__c", "APTS_Portfolio_Name__c", "APTS_Active__c",
            "APTS_Service_Business_Unit__c", "Name"]


def _org(ext_id, price, active="TRUE"):
    return ["[APTS_Service_Price_Matrix__c]", ext_id, "DE", "CVG1", "SVC1", "n", "Recurring",
            price, "10", "5", "0", "FALSE", "EUR", "12", "60", "PB",
            "whatever", "PF", active, "BU", "nm"]


def test_l07_prep_and_deltas():
    new = _df([
        _spm("DE", "CVG1", "SVC1", "Recurring", "187.970833333333"),
        _spm("DE", None, "SVC2", "Recurring", "1"),      # null CVG -> "null" in ext id
        _spm("DE", "CVG9", "SVC9", "One-Time", "7"),     # filtered out
    ], SPM_COLS)
    org = _df([
        _org("SVC1_CVG1_DE", "187.970833333333"),
        _org("GONE_CVGX_DE", "5"),
    ], ORG_COLS)
    out = build_l07(new, org, Config())
    extra = out["Extra"]
    assert list(extra["APTS_Ext_ID__c"]) == ["SVC2_null_DE"]
    assert extra["APTS_Pricebook_Simulation_Date__c"].iloc[0] == "2026-03-09T00:00:00.000+0000"
    assert set(out["Not Matching"]["APTS_Ext_ID__c"]) == {"SVC2_null_DE"}  # price matched SVC1
    deact = out["Extra in cCRM (Deactivate)"]
    assert deact.values.tolist() == [["[APTS_Service_Price_Matrix__c]", "GONE_CVGX_DE", "FALSE"]]


def test_l07_price_compared_numerically_not_textually():
    new = _df([_spm("DE", "CVG1", "SVC1", "Recurring", "10")], SPM_COLS)
    org = _df([_org("SVC1_CVG1_DE", "10.0")], ORG_COLS)
    out = build_l07(new, org, Config())
    assert len(out["Not Matching"]) == 0


def test_l07_itest4_rounds_prices_to_15_significant_digits():
    cfg = Config(org_profile="itest4")
    df = _df([_spm("DE", "CVG1", "SVC1", "Recurring", "187.97083333333299")], SPM_COLS)
    prepped = prep_l07(df, cfg.org_profile)
    assert prepped["APTS_List_Price__c"].iloc[0] == "187.970833333333"
