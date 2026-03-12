from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo-mcp-server")

@mcp.tool()
def get_product_specs(sku: str) -> dict:
    """Return product specs for a given SKU."""
    catalog = {
        "SKU-123": {"name": "Router X1", "wifi": "Wi-Fi 6", "ports": 5, "price_inr": 4999},
        "SKU-999": {"name": "AP Z9", "wifi": "Wi-Fi 7", "ports": 2, "price_inr": 15999},
    }
    print("get_product_specs sku ", sku)
    return catalog.get(sku, {"error": "Unknown SKU"})


@mcp.tool()
def check_inventory(sku: str) -> dict:
    """Return available inventory and ETA."""
    inventory = {
        "SKU-123": {"available": 42, "eta_days": 0},
        "SKU-999": {"available": 0, "eta_days": 7},
    }
    print("check_inventory sku ", sku)
    return inventory.get(sku, {"error": "Unknown SKU"})


if __name__ == "__main__":
    mcp.run(transport="stdio")
