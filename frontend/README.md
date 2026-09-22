# SafetyHome frontend

Responsywna aplikacja React/Vite prezentująca bieżące dane SafetyComponent bezpośrednio z Home Assistanta przez
`@hakit/core`.

Ten plik jest celowo prowadzony po polsku jako instrukcja operatorska frontendu.
Dokumentacja systemowa i wymagania są po angielsku; komendy, ścieżki,
identyfikatory i surowe stany pozostają wspólnym kontraktem technicznym.

## Uruchomienie lokalne

Wymagany jest Node.js 20 zgodnie z `.nvmrc`.

```powershell
nvm install 20
nvm use 20
Copy-Item .env.example .env
npm ci
npm run dev
```

W trybie deweloperskim `VITE_HA_URL` wskazuje instancję Home Assistanta. Aplikacja nie przyjmuje długowiecznego tokenu
w kodzie klienta — `HassConnect` prowadzi normalne logowanie HA.

Do przeglądu wszystkich stanów interfejsu bez logowania można użyć wyłącznie lokalnego trybu demonstracyjnego:

```powershell
npm run dev:mock
```

Tryb demonstracyjny działa tylko przy deweloperskim buildzie Vite i jest jawnie oznaczony w nagłówku. Produkcyjny build
zawsze korzysta z rzeczywistych encji Home Assistanta.

## Historia powiadomień i encji

Na stronie **Historia** lista powiadomień znajduje się nad historią encji.
Pokazuje najnowsze próby przekazania powiadomień do Home Assistanta: aktywację
problemu (`SET`), jego aktualizacje i ponowienia, a także ustąpienie
(`CLEARED`). Usunięcie powiadomienia wskutek przesłonięcia problemu
(`SHADOWED`) jest osobnym zdarzeniem i nie oznacza, że problem ustąpił.

Każdy wpis pokazuje datę i godzinę w lokalnej strefie przeglądarki, usługę
odbiorcy oraz wynik próby. Kliknij wpis, aby zobaczyć treść, poziom pilności,
czas utworzenia i próby, numer próby, informację o przekroczeniu terminu oraz
identyfikatory diagnostyczne. Przyjęcie przez Home Assistanta nie jest
potwierdzeniem dostarczenia na telefon. Dla grupy, np. `notify/all_phones`,
lista pokazuje nazwę usługi; nie ustala jej członków ani konkretnych osób,
które otrzymały wiadomość.

Dziennik pochodzi z `sensor.notification_history`, obejmuje ostatnie 100 prób
dla poszczególnych usług i wyświetla najnowsze wpisy na początku. Nieudana
próba i jej ponowienie mają osobne wpisy. Samo oczekiwanie na odzyskanie
Internetu nie jest próbą wysłania. Historia korzysta z istniejącego zapisu
stanu powiadomień i przy włączonej persystencji przetrwa restart AppDaemona;
wcześniejszy zapis bez dziennika rozpoczyna historię od pustej listy.
Rejestrator Home Assistanta nie jest wymagany do odczytu tej listy.
Historia encji pozostaje poniżej i korzysta z Rejestratora.

### Potwierdzanie powiadomień

Rozwinięta karta aktywnej usterki poziomu L1–L3 na pulpicie zawiera przycisk
**Potwierdź powiadomienie**. SafetyHome przesyła stabilny tag przez
uwierzytelnione zdarzenie Home Assistanta. Potwierdzenie zatrzymuje kolejne
powtórzenia alarmu, ale nie usuwa usterki. Stan **Potwierdzono** pochodzi z
`sensor.notification_delivery_health` i pozostaje widoczny po odświeżeniu
strony. Ta sama operacja jest dostępna w powiadomieniu aplikacji Companion.

### Historia temperatur

Popupy temperatur pobierają historię na żądanie z Rejestratora Home Assistanta.
Repozytorium zawiera wąski przykład allowlisty obejmujący wyłącznie osiem
czujników używanych przez SafetyComponent:
[`docs/examples/home_assistant_recorder_temperature.yaml`](../docs/examples/home_assistant_recorder_temperature.yaml).
Scal listę `include.entities` z istniejącą konfiguracją `recorder`; nie zastępuj
pozostałych reguł `include`/`exclude`. Taki zakres przywraca wykresy temperatur
bez włączania zapisu całej domeny `sensor`. Retencja `purge_keep_days` pozostaje
globalnym ustawieniem Rejestratora i nie jest zmieniana przez przykład.

## Konfiguracja instalacji

Po pierwszym starcie aplikacji otwórz **Konfiguracja**. Panel pokaże szkic
`user_config.yml`; zastąp przykładowe encje i obszary danymi domu albo użyj
**Wczytaj user_config YAML**, aby wczytać istniejący plik `.yml`/`.yaml` w
modelu v2. Import tylko wypełnia formularz. Sprawdź go, zapisz i uruchom
ponownie aplikację, aby wystartował SafetyFunctions.

Strona edytuje włączone komponenty i providery, język, odbiorców powiadomień,
dane lokalizacji, wartości domyślne instalacji oraz rejestry pomieszczeń,
otworów, detektorów i monitorowanych encji. `system_config.yml` jest częścią
wersjonowanego obrazu aplikacji. Cały panel Ingress jest dostępny tylko dla
administratorów Home Assistanta, ponieważ konfiguracja zawiera prywatną
topologię instalacji.

Zapis jest przyjmowany tylko wtedy, gdy dokument nadal ma odczytaną rewizję,
przechodzi walidację modelu v2 i daje się skompilować z dołączoną konfiguracją
systemową. Po zapisie uruchom ponownie aplikację SafetyComponent. Dopiero
kontrolowany start tworzy nowe `apps.yaml` i wykonuje walidację zależną od
bieżących encji Home Assistanta.

## Działania rekomendowane

Karta działania pokazuje instrukcję, powód, źródło, ważność i bieżący etap
wykonania. Zamknięcie zwykłego okna lub drzwi jest czynnością ręczną.
Przycisk potwierdzenia pojawia się wyłącznie dla skonfigurowanej bramy
garażowej i zewnętrznej. Frontend wysyła potwierdzenie do SafetyComponent przez
uwierzytelnione połączenie Home Assistanta; nie wywołuje usługi bramy
bezpośrednio. Nie potwierdzaj akcji, jeżeli nie masz pewności, że ruch bramy jest
bezpieczny.

## Weryfikacja

```powershell
npm test
npm run typecheck
npm run lint -- --max-warnings=0
npm run format:check
npm run build
```

## Deploy do Home Assistanta

Docelowym sposobem wdrożenia jest samodzielny Home Assistant App z katalogu
`safety_component/`. App buduje frontend razem z backendem, udostępnia go przez
uwierzytelniony Ingress i dodaje **Safety Home** z ikoną syreny do panelu
bocznego. Instrukcja instalacji i migracji znajduje się w
[`safety_component/DOCS.md`](../safety_component/DOCS.md).

Poniższy deploy do `/config/www` pozostaje ścieżką zgodności dla instalacji,
które nie zostały jeszcze przeniesione do samodzielnego App.

Home Assistant udostępnia pliki z `/config/www` pod adresem `/local`. Skrypt deploy:

1. wykonuje świeży build,
2. wysyła go przez SFTP do katalogu tymczasowego,
3. sprawdza obecność `index.html`,
4. atomowo podmienia `/config/www/<VITE_FOLDER_NAME>`,
5. przy błędzie podmiany przywraca poprzednią wersję.

Uzupełnij w `.env` wartości `HA_SSH_*`, a następnie:

```powershell
npm run deploy
```

Przy pierwszym wdrożeniu katalog `/config/www` musi już istnieć. Jeśli tworzysz go po raz pierwszy, uruchom ponownie Home
Assistanta przed wykonaniem deployu, aby ścieżka `/local` została udostępniona.

Dla domyślnego `VITE_FOLDER_NAME=SafetyHome` aplikacja będzie dostępna pod:

```text
https://ADRES_HA/local/SafetyHome/index.html
```

Do panelu bocznego można ją dodać w Home Assistant jako dashboard typu **Webpage**. Użyj ścieżki względnej
`/local/SafetyHome/index.html`, aby iframe zawsze miał ten sam origin co aktualny adres Home Assistant — również po
przełączeniu między adresem wewnętrznym i zewnętrznym w Companion App.
Routing używa fragmentu URL (`#/temperature`, `#/history`), dlatego odświeżenie podstrony działa także przy zwykłym
hostingu statycznym.

Alternatywą jest aplikacja HAKit z `html_file_path: www/SafetyHome/index.html` i `spa_mode: true`.

### Bezpieczeństwo sekretów

- Home Assistant udostępnia pliki z `/config/www` publicznie pod `/local`; nie są one chronione logowaniem HA. Produkcyjny
  bundle nie może zawierać sekretów, a dostęp do stanów nadal odbywa się przez OAuth Home Assistanta.
- Nie umieszczaj tokenów ani danych SSH w zmiennych z prefiksem `VITE_` — trafiają do publicznego kodu klienta.
- `HA_SYNC_TOKEN` służy tylko do lokalnego `npm run sync`.
- Do SSH preferuj `HA_SSH_PRIVATE_KEY_PATH`; hasło jest obsługiwane jako wariant zapasowy.
- `HA_SSH_HOST_FINGERPRINT` jest wymagany i musi mieć standardowy format `SHA256:<base64>`. Odcisk można odczytać
  z zaufanego wpisu `known_hosts` albo konsoli hosta. Wynik `ssh-keyscan` należy porównać z zaufanym źródłem — sam skan
  sieci nie potwierdza tożsamości serwera.

## Synchronizacja typów HA

Ustaw `HA_SYNC_TOKEN` i uruchom:

```powershell
npm run sync
```

Wygenerowany plik `src/supported-types.d.ts` rozszerzy typy encji oraz usług `@hakit/core`.

Zasady zgłaszania zmian, wymagane testy i oczekiwania dla pull requestów opisuje
[główny przewodnik współpracy](../CONTRIBUTING.md).
