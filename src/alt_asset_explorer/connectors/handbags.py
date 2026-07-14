from alt_asset_explorer.connectors.rally_manual import load_comps

CATEGORY = "handbags"


def load_manual_template():
    return load_comps().query("category == @CATEGORY").copy()
