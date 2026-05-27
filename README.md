# Dokumentacja techniczna mikroserwisu ML

**Zespół:** Sakura
**Projekt:** Sugerowanie cen noclegów dla nowo dodawanych lokali w Rzymie

## 1. Cel projektu

Głównym celem projektu jest wdrożenie mikroserwisu wspomagającego wycenę lokali na platformie Nocarz. Mikroserwis działa jako niezależny komponent backendowy - przyjmuje dane wejściowe z formularza, dokonuje wyboru modelu w ramach testu A/B, loguje zdarzenie i zwraca wynik w formacie JSON.

## 2. Stos technologiczny

Mikroserwis został zrealizowany w języku **Python (3.10+)** z użyciem frameworka **FastAPI** i serwera **Uvicorn**, którego asynchroniczna architektura pozwala na płynną obsługę wielu równoległych żądań od różnych użytkowników. Utrwalanie danych jest realizowane za pomocą plików w formacie `.jsonl`, całość została skonteneryzowana przy użyciu platformy **Docker**, co gwarantuje pełną izolację zależności i powtarzalne wdrożenie.

*Nie mam pewności czy ten docker jest potrzebny, jeśli nie to go usunę stąd*

## 3. Działanie mikroserwisu

1. **Start serwera** - podczas uruchamiania serwera, aplikacja jednorazowo wczytuje do pamięci modele zapisane przez warstwę ML: model bazowy oraz model docelowy.
2. **Odbiór żądania** - serwer nasłuchuje na endpoincie `/predict` i przyjmuje strukturę JSON z parametrami lokalu.
3. **Eksperyment A/B**
    * **Wariant A** zapytanie jest przekazywane do modelu bazowego z prawdopodobieństwem `...`
    * **Wariant B** zapytanie jest przekazywane do modelu docelowego z prawdopodobieństwem `...`
4. **Wyznaczenie predykcji przez model** - wybrany model przetwarza cechy wejściowe i wylicza `...` (tutaj będzie trzeba doprecyzować czy wylicza konkretną cenę, przedział, czy może informację słowną)
5. **Zapis logów** - każde zapytanie jest logowane i trzymane w pliku `...` . Log zawiera: znacznik czasu, unikalne ID zapytania, przekazane w zapytaniu parametry lokalu, informację o wylosowanym wariancie oraz zwróconą przez model predykcję.
6. **Odpowiedź** - serwer odsyła klientowi obiekt JSON zawierający wyznaczoną cenę/klasę (tu też trzeba będzie doprecyzować). Sam wybór modelu jest całkowicie niewidoczny dla użytkownika zewnętrznego.

## 4. API

### Endpoint: `POST /predict`

**Przykładowy payload wejściowy:**
*Tutaj będzie trzeba dać dane ktore są przyjmowane przez modele*

```json
{
  # ...
}
```

**Przykładowa odpowiedź serwera:**
*Tutaj analogicznie jak w przypadku danych wejściowych też będzie trzeba dać format odpowiedzi generowanej przez model*

```json
{
    # ...
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
  "accommodates": 4,
  "bedrooms": 2,
  "bathrooms": 1
}' http://localhost:8000/predict
```

*To tez sie zmieni bo obstawiam ze tutaj moze byc za duzo tych danych*
