# Dokumentacja techniczna mikroserwisu ML

**Zespół:** Sakura <br>
**Projekt:** Sugerowanie cen noclegów dla nowo dodawanych lokali w Rzymie

## 1. Cel projektu

Głównym celem projektu jest wdrożenie mikroserwisu wspomagającego wycenę lokali na platformie Nocarz. Mikroserwis działa jako niezależny komponent backendowy - przyjmuje dane wejściowe z formularza, dokonuje wyboru modelu w ramach testu A/B, loguje zdarzenie i zwraca wynik w formacie JSON.

## 2. Stos technologiczny

Mikroserwis został zrealizowany w języku **Python (3.12+)** z użyciem frameworka **FastAPI** i serwera **Uvicorn**, którego asynchroniczna architektura pozwala na płynną obsługę wielu równoległych żądań od różnych użytkowników. Utrwalanie danych jest realizowane za pomocą plików w formacie `.jsonl`, całość została skonteneryzowana przy użyciu platformy **Docker**, co gwarantuje pełną izolację zależności i powtarzalne wdrożenie.

## 3. Działanie mikroserwisu

1. **Start serwera** - podczas uruchamiania serwera, aplikacja jednorazowo wczytuje do pamięci modele zapisane przez warstwę ML: model bazowy oraz model docelowy.
2. **Odbiór żądania** - serwer nasłuchuje na endpoincie `/predict` i przyjmuje strukturę JSON z parametrami lokalu.
3. **Eksperyment A/B** - wariant A obsługiwany jest przez model bazowy, natomiast wariant B - przez model docelowy. Przydział do wariantu jest **deterministyczny i trwały**: serwer haszuje adres IP klienta za pomocą funkcji MD5 i na tej podstawie wylicza wartość z przedziału 0-99. Dzięki takiemu podejściu ten sam użytkownik zawsze trafia do tego samego wariantu, niezależnie od liczby wykonanych zapytań. Procent ruchu kierowany do modelu docelowego jest skonfigurowany w pliku `config.json` poprzez parametr `target_model_probability`.  
4. **Wyznaczenie predykcji przez model** - wybrany model przetwarza cechy wejściowe lokalu i zwraca sugerowaną cenę (`predicted_price_exact`) wraz z doradczym przedziałem cenowym (`advisory_range_min` / `advisory_range_max`) oraz wartościami porównawczymi względem mediany cen w okolicy i w mieście.
5. **Zapis logów** - każde zapytanie jest logowane i dopisywane do pliku `logs_ab_test.jsonl`. Log zawiera: znacznik czasu, adres IP klienta, przypisany wariant A/B, przekazane w zapytaniu parametry lokalu (`input_features`) oraz pełny wynik zwrócony przez model (`prediction_result`).
6. **Odpowiedź** - serwer odsyła klientowi obiekt JSON z wyznaczoną ceną, przedziałem doradczym i metadanymi predykcji. Wybór modelu (A czy B) jest całkowicie niewidoczny dla klienta zewnętrznego - struktura odpowiedzi jest identyczna niezależnie od wariantu.

## 4. API

### Endpoint: `POST /predict`

**Pola wymagane:** `latitude`, `longitude`, `accommodates`
**Pola opcjonalne:** `bedrooms`, `bathrooms`, `beds`, `room_type`, `amenities`, `minimum_nights`, `host_is_superhost`, `instant_bookable`, `name`, `description`, `id`

**Przykładowy payload wejściowy:**

```json
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
  "host_is_superhost": false,
  "instant_bookable": false
}
```

**Przykładowa odpowiedź serwera:**

```json
{
  "id": 2737,
  "status": "SUCCESS",
  "message": "Standard prediction applied.",
  "segment_used": "target_small",
  "predicted_price_exact": 60.89,
  "advisory_range_min": 51.0,
  "advisory_range_max": 71.0,
  "comparisons": {
    "neighborhood_median_baseline": 115.0,
    "global_city_median": 115.0
  },
  "prediction_time_ms": 40.66,
  "ab_variant": "B_Target",
  "client_ip": "172.18.0.1",
  "current_prob_config": 70
}
```

## 5. Instrukcja uruchomienia

Dzięki pełnej konteneryzacji, środowisko mikroserwisu można uruchomić na dowolnej maszynie za pomocą polecenia:

```bash
docker compose up --build
```

Po wykonaniu polecenia, serwer produkcyjny staje się dostępny pod adresem `http://localhost:8000`.
Przykładowe wywołanie:

```bash
curl -X POST -H "Content-Type: application/json" -d '{
  "latitude": 41.9028,
  "longitude": 12.4964,
  "accommodates": 4,
  "bedrooms": 2.0,
  "bathrooms": 1.5,
  "beds": 2,
  "room_type": "Entire home/apt"
}' http://localhost:8000/predict
```

## 6. Ewaluacja eksperymentu A/B

Skrypt `test_ab.py` symuluje ruch produkcyjny: generuje pulę unikalnych adresów IP i z każdego z nich wysyła serię zapytań do `/predict` ze zróżnicowanymi parametrami lokalu. Dodatkowo skrypt wykonuje sanity-check.

Notatnik `ab_test_evaluation.ipynb` zawiera:
- weryfikację rozkładu ruchu między wariantami,
- ocenę wydajności generowania predykcji zgodnie z SLA (≤ 500 ms).

## 7. Testy automatyczne

Poprawność działania mikroserwisu jest dodatkowo sprawdzana za pomocą testów jednostkowych, które weryfikują m.in.:
- walidację danych wejściowych (brak wymaganych pól skutkuje odpowiedzią `422`),
- kompletność i poprawność struktury odpowiedzi zwracanej przez `/predict`,
- determinizm przydziału do wariantu (ten sam adres IP zawsze trafia do tego samego wariantu),
- zgodność przydziału z logiką haszowania MD5 opisaną w sekcji 3,
- spójność wartości `current_prob_config` zwracanej w odpowiedzi z konfiguracją w `config.json`,
- pokrycie obu wariantów przez pulę różnych adresów IP.

W celu uruchomienia testów należy uruchomić poniższe komendy:

```bash
pip install -r tests/requirements-dev.txt
pytest tests/ -v
```
