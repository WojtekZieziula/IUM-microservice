import pandas as pd
import numpy as np
import folium
from folium.plugins import HeatMap
import warnings

warnings.filterwarnings('ignore')

ROME_LAT, ROME_LON = 41.89790, 12.47940

def prepare_spatial_data(df):
    df = df.copy()
    
    df["price"] = df["price"].astype(str).str.replace(r"[\$,]", "", regex=True)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
        
    df = df.dropna(subset=["price", "latitude", "longitude"])
    
    if "segment" not in df.columns:
        amenities = df.get("amenities", pd.Series("")).fillna("").astype(str).str.lower()
        is_premium = (
            (df.get("bedrooms", 0) >= 3) | 
            (df.get("property_type", "").astype(str).str.contains("villa", case=False, na=False)) |
            (amenities.str.contains("pool")) | 
            (amenities.str.contains("hot tub"))
        )
        df["segment"] = np.where(is_premium, "premium", "standard")
        
    return df

def generate_heatmap(csv_path="listings.csv", price_cutoff=300):
    print(f"Loading data from {csv_path}...")
    try:
        df_raw = pd.read_csv(csv_path, low_memory=False)
    except FileNotFoundError:
        print(f"ERROR: Could not find '{csv_path}'. Check file path.")
        return
    
    df = prepare_spatial_data(df_raw)
    
    filtered_df = df[df["segment"] != "premium"].copy()
    
    price_cutoff_value = float(price_cutoff)
    pricy_listings = filtered_df[filtered_df["price"] <= price_cutoff_value]
    cutoff_desc = f"Fixed max price cutoff (<= ${price_cutoff_value:.2f})"
    
    if pricy_listings.empty:
        print(f"WARNING: No listings meet the selected cutoff: {cutoff_desc}")
        return
    
    mid_lat = pricy_listings["latitude"].mean()
    mid_lon = pricy_listings["longitude"].mean()
    
    print(f"Filter:        Excluded 'Premium' listings")
    print(f"Price Cutoff:  {cutoff_desc}")
    print(f"Sample Size:   {len(pricy_listings)} listings")
    print(f"Center Point:  ({mid_lat:.5f}, {mid_lon:.5f})")
    
    print("[INFO] Generating interactive heatmap...")
    m = folium.Map(location=[ROME_LAT, ROME_LON], zoom_start=13, tiles="CartoDB positron")
    
    heat_data = pricy_listings[["latitude", "longitude", "price"]].values.tolist()
    HeatMap(heat_data, radius=14, blur=10, max_zoom=13).add_to(m)
    
    popup_label = cutoff_desc
    folium.Marker(
        location=[mid_lat, mid_lon],
        popup=f"<b>Center of {popup_label}</b><br>Avg Price: ${pricy_listings['price'].mean():.2f}",
        icon=folium.Icon(color="red", icon="star", prefix="fa"),
        tooltip="Click for stats"
    ).add_to(m)
    
    output_file = "rome_price_center_heatmap.html"
    m.save(output_file)
    print(f"Heatmap saved to '{output_file}'")

if __name__ == "__main__":
    generate_heatmap("listings.csv", price_cutoff=300)