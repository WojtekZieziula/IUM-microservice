import requests
import random
from collections import Counter, defaultdict

URL = "http://localhost:8000/predict"
NUM_USERS = 1000
REQUESTS_PER_USER = 5

AREAS = ["Trastevere", "Colosseum", "Piazza Navona", "Vatican", "Termini Station", "Campo de' Fiori"]

NAME_TEMPLATES = [
    "Cozy room near {area}",
    "Charming apartment in {area}",
    "Bright flat with a view of {area}",
    "Quiet studio close to {area}",
    "Spacious home in the heart of {area}",
]

DESCRIPTION_TEMPLATES = [
    "A short walk from {area}, perfect for exploring Rome on foot. Quiet at night, lively during the day.",
    "Located minutes from {area} with easy access to public transport, shops and restaurants nearby.",
    "Recently renovated space close to {area}. Great for both short city breaks and longer stays.",
    "Comfortable accommodation a few minutes from {area}, ideal base for sightseeing in Rome.",
]

AMENITIES_POOL = [
    "Wifi", "Kitchen", "Air conditioning", "Heating", "Washer", "Dryer",
    "Free parking on premises", "Free street parking", "Elevator", "Pool",
    "Hot tub", "Dedicated workspace", "TV", "Iron", "Hangers", "Hair dryer",
    "Essentials", "Shampoo", "Bed linens", "Coffee maker", "Refrigerator",
    "Microwave", "Dishwasher", "Oven", "Stove", "Dining table",
    "Long term stays allowed", "Luggage dropoff allowed", "Host greets you",
    "Smoke alarm", "Carbon monoxide alarm", "First aid kit", "Fire extinguisher",
    "Patio or balcony", "Garden view", "City skyline view", "Gym",
    "Private entrance", "Bathtub", "Cleaning products",
]

print(f"Starting simulation: {NUM_USERS} users x {REQUESTS_PER_USER} requests = {NUM_USERS * REQUESTS_PER_USER} total requests...")

user_ips = set()
while len(user_ips) < NUM_USERS:
    user_ips.add(
        f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 255)}"
    )
user_ips = list(user_ips)

results_variant = []
ip_to_variants = defaultdict(set)

for ip in user_ips:
    for _ in range(REQUESTS_PER_USER):
        headers = {"X-Forwarded-For": ip}

        accommodates = random.randint(1, 8)
        bedrooms = float(max(0, min(4, accommodates // 2 + random.choice([-1, 0, 0, 1]))))
        beds = max(1, min(8, accommodates + random.choice([-1, 0, 0, 1])))
        bathrooms = round(max(1.0, min(3.0, bedrooms + random.choice([-0.5, 0.0, 0.0, 0.5]))), 1)

        area = random.choice(AREAS)
        name = random.choice(NAME_TEMPLATES).format(area=area)
        description = random.choice(DESCRIPTION_TEMPLATES).format(area=area)
        amenities = random.sample(AMENITIES_POOL, k=random.randint(5, len(AMENITIES_POOL)))

        payload = {
            "latitude": round(random.uniform(41.8, 41.95), 4),
            "longitude": round(random.uniform(12.4, 12.6), 4),
            "accommodates": accommodates,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "beds": beds,
            "room_type": random.choice(["Entire home/apt", "Private room", "Shared room", "Hotel room"]),
            "name": name,
            "description": description,
            "amenities": amenities,
            "minimum_nights": random.choice([1, 2, 3, 7, 14, 30]),
            "instant_bookable": random.choice([True, False]),
            "host_is_superhost": random.choice([True, False]),
        }

        try:
            response = requests.post(URL, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                variant = data["ab_variant"]
                results_variant.append(variant)
                ip_to_variants[ip].add(variant)
            else:
                print(f"HTTP error: {response.status_code}")
        except Exception as e:
            print(f"Connection error: {e}")

# Summary
counts = Counter(results_variant)
total = sum(counts.values())

print("\n--- A/B EXPERIMENT RESULTS ---")
for variant, count in sorted(counts.items()):
    pct = (count / total) * 100
    print(f"{variant}: {count} requests ({pct:.1f}%)")

# Assignment verification
violations = {ip: variants for ip, variants in ip_to_variants.items() if len(variants) > 1}
print(f"\n--- STICKY ASSIGNMENT CHECK ---")
print(f"Users with consistent variant assignment: {NUM_USERS - len(violations)}/{NUM_USERS}")
if violations:
    print(f"VIOLATIONS (same IP got multiple variants): {len(violations)}")
    for ip, variants in list(violations.items())[:5]:
        print(f"  {ip} -> {variants}")
else:
    print("OK: every user was consistently assigned to one variant.")
