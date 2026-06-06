import json
import numpy as np
import pandas as pd
import joblib
import time
import warnings

warnings.filterwarnings('ignore')

ROME_LAT = 41.89790
ROME_LON = 12.47940

class RomePricingEngine:
    def __init__(self, model_dir="."):
        """Loads the saved model artifacts and historical baselines."""
        print("Initializing Rome Pricing Engine...")
        try:
            self.models = joblib.load(f"{model_dir}/segmented_pricing_models.joblib")
            self.default_model = joblib.load(f"{model_dir}/default_pricing_model.joblib")
            self.feature_cols = joblib.load(f"{model_dir}/model_feature_columns.joblib")
            
            self.baselines = {
                "global_median": 115.0,
                "neighborhood_medians": {
                    "Trastevere": 140.0,
                    "Centro Storico": 160.0,
                    "Esquilino": 90.0
                }
            }
            print("Models and baselines successfully loaded into memory.")
        except FileNotFoundError as e:
            raise RuntimeError(f"Failed to load model artifacts. Error: {e}")

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        r = 6371.0
        p1, p2 = np.radians(lat1), np.radians(lat2)
        a = (np.sin((p2 - p1) / 2) ** 2 + 
             np.cos(p1) * np.cos(p2) * np.sin((np.radians(lon2 - lon1)) / 2) ** 2)
        return r * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    def _check_premium_heuristic(self, row):
        """Zero-Price detection of luxury listings."""
        text_combo = str(row.get('name', '')) + " " + str(row.get('description', ''))
        text_combo = text_combo.lower()
        has_luxury_text = any(word in text_combo for word in ['luxury', 'penthouse', 'mansion', 'exclusive', 'private pool'])
        
        amenities = str(row.get('amenities', '')).lower()
        has_pool_and_tub = 'pool' in amenities and 'hot tub' in amenities
        
        is_massive = int(row.get('bedrooms', 0)) >= 4 or float(row.get('bathrooms', 0)) >= 3.0
        is_luxury_type = any(ptype in str(row.get('property_type', '')).lower() for ptype in ['villa', 'castle', 'resort'])

        return has_luxury_text or has_pool_and_tub or is_massive or is_luxury_type

    def validate_critical_fields(self, record):
        """Checks if the payload contains the absolute minimum required data."""
        critical_fields = ['accommodates', 'latitude', 'longitude']
        missing = [field for field in critical_fields if record.get(field) is None]
        return missing

    def preprocess_payload(self, df):
        """Transforms raw JSON into feature vectors using robust Pandas logic."""
        
        idx = df.index
        df['accommodates'] = df.get('accommodates', pd.Series(2, index=idx)).astype(float)
        df['bedrooms'] = df.get('bedrooms', pd.Series(1, index=idx)).astype(float)
        df['bathrooms_cleaned'] = df.get('bathrooms', pd.Series(1.0, index=idx)).astype(float)
        df['beds'] = df.get('beds', pd.Series(1, index=idx)).astype(float)
        df['host_listings_count'] = df.get('host_listings_count', pd.Series(1, index=idx)).astype(float)
        
        df['bedrooms_safe'] = df['bedrooms'].replace(0, 1)
        df['people_per_bedroom'] = df['accommodates'] / df['bedrooms_safe']
        df['baths_per_person'] = df['bathrooms_cleaned'] / df['accommodates'].replace(0, 1)
        
        prop_type = df.get('property_type', pd.Series('', index=idx)).astype(str)
        df['is_studio'] = ((df['bedrooms'] == 0) | prop_type.str.contains('Studio', case=False)).astype(int)

        df['latitude'] = df.get('latitude', pd.Series(ROME_LAT, index=idx)).astype(float)
        df['longitude'] = df.get('longitude', pd.Series(ROME_LON, index=idx)).astype(float)
        df['dist_center'] = self._haversine(df['latitude'], df['longitude'], ROME_LAT, ROME_LON)

        df['neigh_encoded'] = df.get('neigh_encoded', pd.Series(self.baselines['global_median'], index=idx))
        df['spatial_zone_encoded'] = df.get('spatial_zone_encoded', pd.Series(self.baselines['global_median'], index=idx))

        amenities = df.get('amenities', pd.Series('', index=idx)).astype(str).str.lower()
        df['has_ac'] = amenities.str.contains('air conditioning|ac').astype(int)
        df['has_elevator'] = amenities.str.contains('elevator').astype(int)
        df['has_parking'] = amenities.str.contains('free parking').astype(int)
        
        df['desc_len'] = df.get('description', pd.Series('', index=idx)).astype(str).str.len()
        df['name_len'] = df.get('name', pd.Series('', index=idx)).astype(str).str.len()

        bool_map = {"t": 1, "f": 0, "true": 1, "false": 0, True: 1, False: 0}
        df['instant_bookable_flag'] = df.get('instant_bookable', pd.Series(False, index=idx)).map(bool_map).fillna(0)
        df['superhost_flag'] = df.get('host_is_superhost', pd.Series(False, index=idx)).map(bool_map).fillna(0)
        df['is_pro_host'] = (df['host_listings_count'] > 1).astype(int)

        conditions = [df["accommodates"] <= 2, df["accommodates"] <= 4]
        df["segment"] = np.select(conditions, ["small", "mid"], default="large")

        if 'room_type' in df.columns:
            df = pd.get_dummies(df, columns=["room_type"], drop_first=False)
            
        df_model_ready = df.reindex(columns=self.feature_cols, fill_value=0)
        return df_model_ready, df["segment"].values

    def predict(self, json_payload, force_baseline=False):
        """Validates, processes, and predicts prices for incoming JSON requests."""
        if isinstance(json_data := json_payload, str):
            json_data = json.loads(json_data)
            
        predictions = []
        valid_records = []
        valid_indices = []

        # Validation Pass
        for i, record in enumerate(json_data):
            missing_critical = self.validate_critical_fields(record)
            if missing_critical:
                predictions.append({
                    "id": record.get("id", f"unknown_{i}"),
                    "status": "ERROR_MISSING_DATA",
                    "message": f"Cannot generate estimate. Missing critical required fields: {', '.join(missing_critical)}",
                    "predicted_price_exact": None,
                    "prediction_time_ms": 0.0
                })
            else:
                valid_records.append(record)
                valid_indices.append(i)
                predictions.append(None)

        # Inference Pass (only for valid records)
        if valid_records:
            df_valid = pd.DataFrame(valid_records)
            premium_flags = [self._check_premium_heuristic(row) for _, row in df_valid.iterrows()]
            neighborhoods = [row.get('neighbourhood_cleansed', 'Unknown') for _, row in df_valid.iterrows()]
            
            X, segments = self.preprocess_payload(df_valid)
            
            for list_idx, original_idx in enumerate(valid_indices):
                segment = segments[list_idx]
                is_premium = premium_flags[list_idx]
                neigh = neighborhoods[list_idx]

                start_time_ms = time.perf_counter()
                
                if force_baseline:
                    model = self.default_model
                    segment_label = "baseline_default"
                else:
                    model = self.models.get(segment)
                    if model is not None:
                        segment_label = f"target_{segment}"
                    else:
                        model = self.default_model
                        segment_label = f"fallback_to_baseline_from_{segment}"
                
                pred_price = model.predict(X.iloc[[list_idx]])[0]
                neigh_baseline = self.baselines["neighborhood_medians"].get(neigh, self.baselines["global_median"])
                prediction_time_ms = (time.perf_counter() - start_time_ms) * 1000.0
                
                predictions[original_idx] = {
                    "id": valid_records[list_idx].get("id", f"listing_{original_idx}"),
                    "status": "SUCCESS" if not is_premium else "WARNING_PREMIUM_LISTING",
                    "message": "Standard prediction applied." if not is_premium else "This property triggers luxury heuristics. Our standard ML model may severely undervalue this listing.",
                    "segment_used": segment_label,
                    "predicted_price_exact": round(pred_price, 2),
                    "advisory_range_min": np.floor(pred_price * 0.85),
                    "advisory_range_max": np.ceil(pred_price * 1.15),
                    "comparisons": {
                        "neighborhood_median_baseline": neigh_baseline,
                        "global_city_median": self.baselines["global_median"]
                    },
                    "prediction_time_ms": round(prediction_time_ms, 2)
                }
                
        return predictions


if __name__ == "__main__":
    
    sample_frontend_request = [
        {
            "id": 2737,
            "name": "Elif's room in cozy, clean flat.",
            "description": "10 min by bus you can get to Piazza Venezia or Colosseum. All shops, gym, many trendy&local restaurants and cafes walking distance. <br />30min from beaches of Ostia and Fiumicino airport by direct train. <br />5 min away from metro B line Piramide stop.<br />EATALY is 5 min walking away where you can eat and shop the most quality Italian food from 9 am to midnight.<br />There is big supermarket open 7/24m just 2 min walking.",
            "latitude": 41.87136,
            "longitude": 12.48215,
            "accommodates": 1,
            "bedrooms": 1.0,
            "bathrooms": 1.5,
            "beds": 1.0,
            "room_type": "Private room",
            "amenities": [
                "Dedicated workspace",
                "Bidet",
                "Iron",
                "Toaster",
                "Hangers",
                "Refrigerator",
                "High chair",
                "Dining table",
                "Washer",
                "Portable fans",
                "Microwave",
                "Laundromat nearby",
                "Wifi",
                "Coffee maker",
                "Free street parking",
                "Oven",
                "Dishwasher",
                "Stove",
                "Hot water kettle",
                "Long term stays allowed",
                "Cleaning products",
                "Drying rack for clothing",
                "Blender",
                "Luggage dropoff allowed",
                "Hot water",
                "Heating",
                "Wine glasses",
                "Dishes and silverware",
                "Elevator",
                "Air conditioning",
                "Hot tub",
                "First aid kit",
                "Bed linens",
                "Housekeeping - available at extra cost",
                "Hair dryer",
                "Dryer",
                "Cooking basics",
                "Freezer",
                "Free parking on premises",
                "Outdoor dining area",
                "Patio or balcony",
                "Kitchen"
            ],
            "minimum_nights": 31,
            "host_is_superhost": False,
            "instant_bookable": False
        },
        {
            "id": 3079,
            "name": "Cozy apartment  (2-4)with Colisseum  view",
            "description": "With the view of the Colisseum from the front door and windows and within easy walking distance of the Imperial Forum the apartment is the perfect spot for spending an holiday in Rome.",
            "latitude": 41.895,
            "longitude": 12.49117,
            "accommodates": 4,
            "bedrooms": 1.0,
            "bathrooms": 1.0,
            "beds": 1.0,
            "room_type": "Entire home/apt",
            "amenities": [
                "Paid parking off premises",
                "Dedicated workspace",
                "Iron",
                "Hangers",
                "Refrigerator",
                "Ethernet connection",
                "Wifi",
                "HDTV with standard cable",
                "Coffee maker",
                "Host greets you",
                "Long term stays allowed",
                "Window AC unit",
                "Free washer – In unit",
                "Pocket wifi",
                "Luggage dropoff allowed",
                "Hot water",
                "Heating",
                "Dishes and silverware",
                "Elevator",
                "Bed linens",
                "Hair dryer",
                "Dryer",
                "Shampoo",
                "Essentials",
                "Extra pillows and blankets",
                "Kitchen"
            ],
            "minimum_nights": 31,
            "host_is_superhost": False,
            "instant_bookable": False
        },
        {
            "id": 3079,
            "name": "Cozy apartment  (2-4)with Colisseum  view",
            "description": "With the luxury view of the Colisseum from the front door and windows and within easy walking distance of the Imperial Forum the apartment is the perfect spot for spending an holiday in Rome.",
            "latitude": 41.895,
            "longitude": 12.49117,
            "accommodates": 4,
            "bedrooms": 1.0,
            "bathrooms": 1.0,
            "beds": 1.0,
            "room_type": "Entire home/apt",
            "amenities": [
                "Paid parking off premises",
                "Dedicated workspace",
                "Iron",
                "Hangers",
                "Refrigerator",
                "Ethernet connection",
                "Wifi",
                "HDTV with standard cable",
                "Coffee maker",
                "Host greets you",
                "Long term stays allowed",
                "Window AC unit",
                "Free washer – In unit",
                "Pocket wifi",
                "Luggage dropoff allowed",
                "Hot water",
                "Heating",
                "Dishes and silverware",
                "Elevator",
                "Bed linens",
                "Hair dryer",
                "Dryer",
                "Shampoo",
                "Essentials",
                "Extra pillows and blankets",
                "Kitchen"
            ],
            "minimum_nights": 31,
            "host_is_superhost": False,
            "instant_bookable": False
        },
        {
            "id": 3079,
            "name": "Cozy apartment  (2-4)with Colisseum  view",
            "description": "With the luxury view of the Colisseum from the front door and windows and within easy walking distance of the Imperial Forum the apartment is the perfect spot for spending an holiday in Rome.",
            "longitude": 12.49117,
            "accommodates": 4,
            "bedrooms": 1.0,
            "bathrooms": 1.0,
            "beds": 1.0,
            "room_type": "Entire home/apt",
            "amenities": [
                "Paid parking off premises",
                "Dedicated workspace",
                "Iron",
                "Hangers",
                "Refrigerator",
                "Ethernet connection",
                "Wifi",
                "HDTV with standard cable",
                "Coffee maker",
                "Host greets you",
                "Long term stays allowed",
                "Window AC unit",
                "Free washer – In unit",
                "Pocket wifi",
                "Luggage dropoff allowed",
                "Hot water",
                "Heating",
                "Dishes and silverware",
                "Elevator",
                "Bed linens",
                "Hair dryer",
                "Dryer",
                "Shampoo",
                "Essentials",
                "Extra pillows and blankets",
                "Kitchen"
            ],
            "minimum_nights": 31,
            "host_is_superhost": False,
            "instant_bookable": False
        }
    ]

    json_payload = json.dumps(sample_frontend_request)
    
    try:
        engine = RomePricingEngine(model_dir=".")
        
        print("\n--- STARTING INFERENCE ---")
        start_time = time.time()
        results = engine.predict(json_payload)
        end_time = time.time()
        
        inference_time_ms = (end_time - start_time) * 1000
        
        print("\n--- PREDICTION RESULTS ---")
        for res in results:
            print(f"Listing ID ({res['id']}):")
            print(f"  -> Status             : {res['status']}")
            print(f"  -> Message            : {res['message']}")
            print(f"  -> Inference time     : {res.get('prediction_time_ms', 'N/A')} ms")
            if res['predicted_price_exact']:
                print(f"  -> ML Suggested Price : €{res['predicted_price_exact']} (Range: €{res['advisory_range_min']} - €{res['advisory_range_max']})")
            print("-" * 50)
            
        print(f"\n[METRICS] Successfully processed {len(results)} listings in {inference_time_ms:.2f} milliseconds.")
            
    except Exception as e:
        print(f"\n[ERROR] Inference failed: {e}")