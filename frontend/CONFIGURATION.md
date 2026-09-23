# Konfiguracja SafetyComponent

Ten przewodnik opisuje prywatny plik `user_config.yml` modelu 2. Przykład
składni znajdziesz w [`backend/config/user_config.example.yml`](../backend/config/user_config.example.yml).
Nie kopiuj przykładowych identyfikatorów encji bez sprawdzenia ich w swoim
Home Assistant. Prawdziwego pliku nie umieszczaj w publicznym repozytorium:
zawiera topologię domu, nazwy encji i odbiorców powiadomień.

## Pierwsze uruchomienie i zapis

1. W Home Assistant otwórz **Safety Home → Konfiguracja**. Przy świeżej
   instalacji zobaczysz szkic pliku. Możesz go uzupełnić w formularzu lub
   wybrać **Wczytaj user_config YAML**. Import wypełnia formularz, ale jeszcze
   niczego nie zapisuje.
2. Sprawdź identyfikatory encji i obszarów w **Narzędziach deweloperskich →
   Stany** oraz ustawieniach obszarów Home Assistant. Włącz tylko komponenty,
   dla których masz rzeczywiste źródła danych.
3. Zapisz konfigurację. Panel sprawdza model i możliwość złożenia go z
   `system_config.yml`. Zapis zastępuje bieżący prywatny plik, więc przed
   większą zmianą zachowaj jego kopię.
4. Uruchom ponownie App. Dopiero start stosuje nowy plik i sprawdza obecność
   encji w Home Assistant. Sprawdź log App oraz stan czujników SafetyComponent.
   Nie wywołuj alarmów ani urządzeń wykonawczych tylko po to, by sprawdzić
   formularz.

Plik ma jeden główny klucz `user_config:` i `model_version: 2`. Nie edytuj
generowanego `app_cfg.yaml`. Kompletne reguły walidacji i mapowanie na
konfigurację wykonawczą opisuje [architektura modelu](<../docs/features/Configuration Model - Architecture.md>).

## Skąd pochodzą wartości

`system_config.yml` jest dostarczany z App: definiuje politykę bezpieczeństwa,
profile detektorów, domyślne progi, harmonogramy providerów, horyzonty prognoz
oraz domyślne zagrożenia zewnętrzne. Formularz go nie zmienia. Puste pole w
**Ustawieniach komponentów** oznacza: użyj wartości systemowej. Wartość wpisana
tam dotyczy całej instalacji; ustawienie konkretnego pomieszczenia lub otworu
ma wyższy priorytet. Wartości niepodane są dziedziczone, listy zastępują listę
w całości, a obiekty są scalane. Bieżące wartości i ich uzasadnienie zawiera
[opis konfiguracji systemowej](<../docs/reference/System Configuration.md>).

Szerokość i długość geograficzna są pobierane z konfiguracji Home Assistant
przy **każdym starcie App**. Nie wpisuje się ich do `user_config.yml`.
`timezone`, `country_code` i kody TERYT są nadal danymi instalacji.

## Pola główne

| Pole w `user_config` | Znaczenie |
| --- | --- |
| `model_version` | Wymagana liczba `2`; wersja modelu musi być zgodna z wersją konfiguracji systemowej. |
| `components_enabled` | Pięć wymaganych przełączników: `TemperatureComponent`, `SafetyDoorsComponent`, `ExternalHazardComponent`, `EntityMonitorComponent`, `InternalEnvironmentalHazardMonitorComponent`. Co najmniej jeden musi być włączony. |
| `localization.language` | Język `pl`, `en` albo `de` dla komunikatów i nazw. |
| `localization.entity_names` | Opcjonalna mapa `entity_id: przyjazna nazwa`. Zmienia wyświetlanie, nie techniczne ID, stan ani temat MQTT. |
| `notification.mobile.services` | Co najmniej jedna rzeczywista usługa `notify/<nazwa>`; nie używaj niejednoznacznego `notify/notify`. |
| `notification.mobile.default_url` | Ścieżka w HA otwierana po dotknięciu powiadomienia, np. `/`; domyślnie `/`. |
| `notification.local.light_entity`, `alarm_entity` | Opcjonalne lokalne encje sygnalizacji. Samo ich wpisanie nie upoważnia do testowego włączenia urządzeń. |
| `notification.wan_entity` | Opcjonalna encja informująca o łączności WAN; `null` oznacza brak. |
| `providers.<nazwa>.enabled` | Włącza/wyłącza trzy obsługiwane źródła: `OpenMeteoWeatherApiComponent`, `ImgwWarningsApiComponent`, `OpenMeteoAirQualityApiComponent`. Adresy API i cykl odpytywania pozostają systemowe. |
| `mqtt.legacy_discovery_entity_ids` | Zaawansowana, jednorazowa lista dawnych `sensor.*` do usunięcia retained discovery po zmianie/usunięciu encji. Nie jest to lista aktywnych czujników. Aplikacja nie zna całej historii dawnych ID, więc nie wykrywa ich automatycznie. Po potwierdzonym usunięciu listę można wyczyścić. |
| `installation` | Dane i zasoby konkretnego domu, opisane niżej. |

## Lokalizacja i ustawienia komponentów

| Pole w `installation` | Znaczenie |
| --- | --- |
| `site.timezone` | Strefa IANA wybrana z listy, np. `Europe/Warsaw`; służy do interpretacji lokalnego czasu ostrzeżeń. |
| `site.country_code` | Dwuliterowy kod kraju, np. `PL`. |
| `site.teryt_codes` | Unikalne czterocyfrowe kody powiatów dla ostrzeżeń IMGW; wymagane, gdy włączono External Hazard. |
| `common_entities.outside_temp` | Czujnik temperatury zewnętrznej używany przez komponent temperatury. |
| `component_settings.temperature.low_temperature_c`, `high_temperature_c` | Opcjonalne progi domyślne dla wszystkich pomieszczeń; dolny musi być mniejszy od górnego. Horyzont prognozy jest wyłącznie systemowy. |
| `component_settings.safety_door.timeout_seconds` | Opcjonalny dodatni czas otwarcia drzwi/bramy przed stanem alarmowym. |
| `component_settings.entity_monitor.startup_grace_seconds` | Opcjonalny nieujemny czas ochronny po starcie. |
| `component_settings.entity_monitor.evaluation_interval_seconds` | Opcjonalny dodatni odstęp między ocenami zdrowia encji. |
| `component_settings.entity_monitor.component_overrides` | Wyjątki dla automatycznie monitorowanych zależności komponentów; kluczem jest stabilny identyfikator zależności. Można ustawić `failure_debounce_seconds`, `recovery_debounce_seconds`, `detection_budget_seconds` i `checks`. |
| `component_settings.external_hazard.weather` | Opcjonalne progi `frost_watch_c`, `frost_warning_c`, `gust_watch_m_s`, `gust_warning_m_s`, `precipitation_warning_mm_h`, `persistence_seconds` oraz mapa `hysteresis`. Horyzont i domyślna lista zagrożeń są systemowe. |
| `component_settings.external_hazard.outdoor_air_quality` | Opcjonalne `standard: european_aqi` i dodatni próg `warning_at`. |

## Zasoby domu

Klucze w `rooms`, `openings`, `detectors` i `monitored_entities` są stałymi
identyfikatorami PascalCase, np. `LivingRoom` i `EntranceDoor`. Nie są
tłumaczonymi nazwami wyświetlanymi. `area_id` to identyfikator obszaru HA,
`entity_id` to pełny identyfikator encji HA. Jeden fizyczny otwór deklaruje się
tylko raz, nawet gdy uczestniczy w kilku komponentach.

| Rejestr / pole | Znaczenie |
| --- | --- |
| `rooms.<Room>.area_id` | Obszar HA danego pomieszczenia. |
| `rooms.<Room>.temperature_sensor` | Czujnik temperatury pomieszczenia. |
| `rooms.<Room>.window` | Opcjonalny klucz z `openings` w tym samym obszarze. Tego samego otworu nie można przypisać dwóm pomieszczeniom. |
| `rooms.<Room>.actuator` | Opcjonalna encja `cover.*` zgodna z kontraktem komponentu temperatury. |
| `rooms.<Room>.temperature` | Opcjonalne `low_temperature_c` i `high_temperature_c` tylko dla tego pomieszczenia. |
| `openings.<Opening>.area_id`, `entity_id`, `friendly_name` | Obszar, czujnik otwarcia i nazwa przyjazna dla użytkownika. |
| `openings.<Opening>.kind` | `window`, `door`, `garage_door` lub `gate`. |
| `openings.<Opening>.safety_door` | Obecność obiektu włącza rolę monitorowania drzwi; można nadpisać `timeout_seconds`. Opcjonalne `condition` zawiera `entity_id`, rozłączne listy `pass_states` i `blocked_states`. |
| `openings.<Opening>.external_hazard` | Obecność obiektu włącza rolę zagrożeń zewnętrznych. Opcjonalne `hazards` zawęża zagrożenia do tego otworu. `execution_policy` to `manual` (domyślnie) albo `user_confirmed`; druga wartość wymaga odpowiedniego otworu i encji `cover.*` w `actuator_entity_id`. `confirmation_timeout_seconds` ma zakres 15–600, domyślnie 120. |
| `detectors.<Detector>` | Wymaga `area_id`, `entity_id`, `friendly_name`, `hazard` (`smoke`, `flammable_gas`, `carbon_monoxide`) i `profile` z konfiguracji systemowej. `gas_identity` jest wymagane tylko dla gazu palnego. `enabled` domyślnie `true`. |
| `monitored_entities.<Dependency>` | **Dodatkowa** encja niebędąca już zależnością innego komponentu. Wymaga `entity_id` i `description`; opcjonalne `area_id`, `enabled`, czasy debounce, budżet detekcji i `checks`. Encje używane przez komponenty są monitorowane automatycznie. |

Obiekt `checks` może zawierać `freshness` (`timestamp_source`, dodatni
`max_silence_seconds`), `required_value` (`target`, domyślnie `state`),
`allowed_values` (niepusta lista `values`, opcjonalny `target`), `finite_number`,
`numeric_range` (przynajmniej `minimum` albo `maximum`) oraz `rate_of_change`
(`window_seconds`, `min_samples` i limit wzrostu/spadku na minutę). `target`
wybiera stan lub atrybut. Czasy kontroli nie mogą przekroczyć zadanego budżetu
detekcji. Szczegółowe ograniczenia opisuje [kontrakt modelu](<../docs/features/Configuration Model - Architecture.md>).

## Przy zmianie istniejącej konfiguracji

- Najpierw zachowaj prywatną kopię obecnego pliku. Import nie jest migracją
  starego formatu: nowy model odrzuca nieznane pola.
- Sprawdź, czy dane przenoszone z `system_config.yml` odpowiadają dotychczasowej
  polityce. Usunięcie lokalnego progu lub listy oznacza zastosowanie wartości
  systemowej, co może zmienić ocenę zagrożeń.
- Po zapisie i restarcie sprawdź log App, stan providerów i encji. Błędna albo
  niedostępna encja nie jest pozytywnym dowodem, że zagrożenie ustało.
