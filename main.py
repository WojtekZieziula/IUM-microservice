from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List
import datetime
import json
import hashlib

from model.regression_interface import RomePricingEngine

ENGINE = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global ENGINE
    print("Loading ML models...")
    try:
        ENGINE = RomePricingEngine(model_dir="./model")
        print("Models loaded successfully!")
    except Exception as e:
        print(f"ERROR: Could not load models. {e}")

    yield

    print("Shutting down, cleaning up resources...")
    ENGINE = None

app = FastAPI(
    title="Nocarz ML API",
    description="Microservice for property valuation with Sticky A/B testing",
    version="1.0",
    lifespan=lifespan
)

class ListingData(BaseModel):
    # Required fields
    latitude: float   
    longitude: float  
    accommodates: int 
    
    # Optional fields
    id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    bedrooms: Optional[float] = None
    bathrooms: Optional[float] = None
    beds: Optional[float] = None
    room_type: Optional[str] = None
    amenities: Optional[List[str]] = None
    minimum_nights: Optional[int] = None
    host_is_superhost: Optional[bool] = None
    instant_bookable: Optional[bool] = None

def get_target_model_probability() -> int:
    """
    Reads target model probability from config.json (by default it's set to 50%)
    """
    try:
        with open("config.json", "r") as file:
            config = json.load(file)
            return config.get("target_model_probability", 50)
    except (FileNotFoundError, json.JSONDecodeError):
        return 50

@app.post("/predict")
def predict_price(listing: ListingData, request: Request):
    """
    Main endpoint. Routes via deterministic A/B test based on Client IP.
    """
    if not ENGINE:
        raise HTTPException(status_code=500, detail="Pricing Engine has not been loaded on the server.")

    client_ip = request.headers.get("X-Forwarded-For", request.client.host) or "unknown_ip"
    target_model_probability = get_target_model_probability()

    ip_hash = int(hashlib.md5(client_ip.encode('utf-8')).hexdigest(), 16)
    hash_bucket = ip_hash % 100

    is_baseline = (hash_bucket >= target_model_probability)
    variant = "A_Baseline" if is_baseline else "B_Target"

    listing_dict = listing.model_dump(exclude_unset=True)
    json_payload = [listing_dict]

    try:
        results = ENGINE.predict(json_payload, force_baseline=is_baseline)
        result = results[0]
        
        if result.get("status") == "ERROR_MISSING_DATA":
             raise HTTPException(status_code=400, detail=result["message"])

        result["ab_variant"] = variant
        result["client_ip"] = client_ip
        result["current_prob_config"] = target_model_probability

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")

    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "client_ip": client_ip,
        "ab_variant": variant,
        "input_features": listing_dict,
        "prediction_result": result
    }

    with open("logs_ab_test.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    return result
