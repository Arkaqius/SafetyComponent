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

## Weryfikacja

```powershell
npm test
npm run typecheck
npm run lint -- --max-warnings=0
npm run format:check
npm run build
```

## Deploy do Home Assistanta

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
