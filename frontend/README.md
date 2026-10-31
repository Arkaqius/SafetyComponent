# SafetyHome frontend

Responsywna aplikacja React/Vite prezentująca bieżące dane SafetyComponent bezpośrednio z Home Assistanta przez
`@hakit/core`.

Ten plik jest celowo prowadzony po polsku jako instrukcja operatorska frontendu.
Dokumentacja systemowa i wymagania są po angielsku; komendy, ścieżki,
identyfikatory i surowe stany pozostają wspólnym kontraktem technicznym.

## Scenariusze bezpieczeństwa

Widok **Scenariusze bezpieczeństwa** pozwala uruchomić wybrany zestaw kontroli,
anulować trwające wykonanie i przeglądać ostatnie 20 raportów. Każde ponowienie
tworzy nowy raport. Wynik OK dotyczy chwili kontroli, a brak danych jest widoczny
oddzielnie od wykrytych problemów. Wykonania przerwane restartem nie są sukcesem.
Przy braku połączenia raporty pozostają historyczne; po przekroczeniu czasu
oczekiwania odśwież historię przed ponownym uruchomieniem.

Scenariusze konfiguruje się w **Konfiguracja → Scenariusze bezpieczeństwa**,
zgodnie z [instrukcją konfiguracji](CONFIGURATION.md). Kontrola nie steruje
urządzeniami ani nie kasuje istniejących alarmów. Powiadomienia zewnętrzne można
powiązać z wydarzeniem zakończenia opisanym w
[architekturze](../docs/features/Safety%20Routines%20-%20Architecture.md).

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

Tryb demonstracyjny działa tylko przy deweloperskim buildzie Vite. Informację
o lokalnych danych testowych znajdziesz w **Pomocy** i nagłówkach podstron;
pulpit pomija to oznaczenie. Produkcyjny build zawsze korzysta z rzeczywistych
encji Home Assistanta.

## Widok podstawowy i rozszerzony

Nowa przeglądarka otwiera **Podstawowy**: bieżącą ocenę domu, najpilniejsze
aktywne zdarzenie z lokalizacją, zalecenie oraz ograniczenia monitoringu.
Typowa treść mieści się na jednym ekranie telefonu. Długie instrukcje pozostają
widoczne w całości i mogą wymagać przewinięcia. Przycisk zalecenia otwiera jego
szczegóły i dostępne potwierdzenia; sam nie wykonuje działania.

**Rozszerzony** udostępnia wszystkie zdarzenia, pomiary, wykresy, historię,
diagnostykę i konfigurację. Przełącznik w nagłówku zapamiętuje wybór lokalnie
w przeglądarce. Bezpośredni odnośnik do diagnostyki otwiera widok rozszerzony;
powrót do podstawowego prowadzi na pulpit. Brak połączenia i ograniczenia danych
są widoczne w obu widokach. Zmiana widoku nie wysyła poleceń do Home Assistanta.

Nazwy urządzeń i wejść pochodzą z `friendly_name` Home Assistanta; interfejs
zachowuje ich brzmienie. Znane stany, przyczyny i funkcje systemu mają polskie
etykiety. Gdy nazwy lub opisu brakuje, widok pokazuje tę niepewność zamiast
tworzyć nazwę z technicznego identyfikatora. Poprawne wartości liczbowe, także
ujemne, pozostają odczytami. Podstawowe informacje o pokryciu i działaniach
wskazują funkcję oraz urządzenie zrozumiałymi nazwami. Surowe identyfikatory,
kody i zapis **Freeze frame** są dostępne w szczegółach diagnostycznych widoku
rozszerzonego.

## Ogrzewanie

W widoku rozszerzonym strona **Ogrzewanie** pokazuje skonfigurowane wejścia,
ich jakość, obserwowaną fazę pracy i zakres kontroli. Nazwy źródeł pochodzą
z Home Assistanta, a brak wiarygodnych danych pozostaje widoczny.

Domyślny zakres obejmuje diagnostykę dostępności i poprawności wejść (R01).
Po dopuszczeniu odpowiedniego profilu dostępne są również: bieżąca usterka
urządzenia (R02), brak żądania grzania (R03), brak odpowiedzi kotła (R04),
niewystarczający wzrost temperatury zasilania (R05), nieosiąganie temperatury
zadanej (R06) i
informacja serwisowa (R13). Wymagają kompletnych, świeżych i właściwie opisanych
wejść. R05/R06 wymagają historii nowych pomiarów i jawnych progów; powtarzanie
starych odczytów nie potwierdza poprawy. Dostępne są także kontrole obiegu i
dostarczania ciepła (R07–R09), temperatury kotła (R10–R11) i częstych uruchomień
palnika (R12). Wymagają potwierdzonych pomiarów i progów dla danej instalacji.
R12 pozostaje informacją L4 bez pogarszania ogólnego stanu systemu. Aktualizacja
nie włącza żadnej nowej reguły automatycznie. Poprawny odczyt lub brak aktywnego alarmu nie
potwierdza dostarczania ciepła ani bezpiecznej temperatury kotła.
Mapowanie dowolnych urządzeń opisuje
[konfiguracja wejść ogrzewania](CONFIGURATION.md#wejścia-monitoringu-ogrzewania).

## Zdrowie systemu: monitorowane encje i baterie

Widok **Rozszerzony → Zdrowie systemu** ma cztery podzakładki:
**Monitorowane encje**, **Baterie**, **Platforma** oraz **Testy i powiadomienia**.
Wybrana podzakładka jest zapisana w adresie strony, więc można wrócić do niej
po odświeżeniu, użyciu Wstecz/Dalej lub udostępnić bezpośredni odnośnik.
Fragment adresu po `#` to `/functional-safety?tab=entities` (domyślna),
`/functional-safety?tab=batteries`, `/functional-safety?tab=platform`
lub `/functional-safety?tab=tests`. Przełączenie podzakładki zachowuje filtry i wybór
wiersza do czasu przeładowania strony. Gdy fokus jest na podzakładce,
strzałki lewo/prawo zmieniają wybór, a Home/End przechodzą do pierwszej/ostatniej.

Podzakładka **Monitorowane encje** pokazuje wyłącznie źródła objęte diagnostyką
SafetyComponent: wpisy użytkownika
i zależności komponentów. Obejmuje również źródła sprawne i niedostępne.
Liczba zależy od konfiguracji instalacji; nie jest liczbą wszystkich encji HA
ani urządzeń w domu. Użyj wyszukiwania i filtrów oceny, pochodzenia,
właściciela lub pomieszczenia; rozwiń źródło, aby sprawdzić identyfikator,
kontrole, przyczyny i czasy. Osobna pozycja **Encje i urządzenia** oraz ogólny
spis encji HA nie są częścią nawigacji. Starszy odnośnik `/entities` prowadzi
do **Zdrowia systemu**.

Podzakładka **Baterie** na tej samej stronie pokazuje stan konserwacji baterii,
poprawne wartości procentowe oraz jakość źródeł. Wyszukuj po nazwie urządzenia,
kluczu diagnostycznym lub identyfikatorze encji źródłowej. Filtr oceny wybiera
baterie niskie, prawidłowe lub bez wiarygodnej oceny. Domyślna kolejność to
najpierw niskie baterie, potem nieznane oceny, na końcu prawidłowe. Możesz też
sortować po nazwie lub rosnąco/malejąco po procencie; nieznane wartości
pozostają na końcu. Rozwiń wiersz, aby sprawdzić źródła, surowe odczyty oraz
czasy raportu i kontaktu. Niepoprawny odczyt nie jest przedstawiany jako
wiarygodny procent.

Lista korzysta z pełnych danych API. Jeżeli dostępne jest tylko ograniczone
podsumowanie encji HA, strona pokazuje to ograniczenie i liczbę pominiętych
baterii. Brak wiersza w takim podsumowaniu nie potwierdza poprawnej baterii.
Po błędzie API strona korzysta z ograniczonego podsumowania zamiast nadal
przedstawiać zapamiętaną pełną odpowiedź jako aktualną. Ostrzeżenie pozostaje
widoczne również po filtrowaniu i przy braku pasujących wyników.
Lista monitorowanych encji pozostaje niezależna od listy baterii. Wybór
monitorowanych urządzeń bateryjnych nadal znajduje się w **Konfiguracji**.

Monitor baterii ufa pojedynczemu `sensor.*_last_seen` powiązanemu z tym samym
urządzeniem. Świeży kontakt pozwala wykorzystać ostatni poprawny stan baterii,
nawet gdy procent ani czas raportu baterii się nie zmieniają. Domyślny limit
kontaktu wynosi 24 godziny. Kontakt nie naprawia niedostępnej encji, błędnej
jednostki ani niepoprawnej wartości. Brak poprawnego czasu wybranego kontaktu
lub kilka pasujących źródeł oznacza brak wiarygodnej oceny; system nie zastępuje
wtedy kontaktu czasem aktualizacji baterii. Dla urządzeń bez takiego źródła
pozostaje sprawdzanie czasu raportu baterii (`last_reported`, a przy jego braku
`last_updated`). Szczegóły rozróżniają czasy kontaktu i raportu baterii.

Komunikat **oceny wymagają weryfikacji** dotyczy nieznanych ocen usterek,
stanów działań lub poziomu systemu, a nie liczby monitorowanych encji.
Podsumowanie pokazuje ten podział. W **Usterki i diagnostyka → Zdarzenia i stan
oceny** domyślny filtr **Wymagające uwagi** obejmuje również nieocenione
(`NOT_EVALUATED`) i niewiarygodne oceny; nie oznaczają one potwierdzonej awarii.

## Kontakt czujników i dane alarmowe

Karty detektorów pokazują **Ostatni kontakt urządzenia** osobno od obserwacji
stanu alarmowego. Kontakt pochodzi z pojedynczej encji `sensor.*_last_seen`
przypisanej w Home Assistant do tego samego urządzenia co czujnik binarny.
Brak jednoznacznego źródła lub poprawnego czasu daje **Brak potwierdzonych danych**.

Kontakt jest zapisem wcześniejszej wiadomości urządzenia. Może dotyczyć baterii
lub innego odczytu i nie potwierdza bieżącego braku zagrożenia ani dostępności
stanu alarmowego. Dlatego czujnik zalania może pokazywać czas kontaktu razem
z oznaczeniem **Brak danych alarmowych**. Przy nieznanym stanie bez zapamiętanego
aktywnego alarmu pole **Alarm zagrożenia** pokazuje **Nie można ocenić**.
Kontakt nie usuwa aktywnego alarmu ani usterki monitoringu.

## Prognoza temperatury i kondycja jej danych

W widoku **Temperatura** sprawdź ostatnią prognozę pomieszczenia razem z
horyzontem, dolnym i górnym progiem oraz czasem oceny. Te dane pochodzą z
backendu, z atrybutu `forecast_evaluation` istniejących encji
`<source>_low_threshold` i `<source>_high_threshold`. Panel nie wylicza
samodzielnie alarmu z temperatury i tempa zmian.

Wynik ostatniej prognozy jest oddzielony od zakwalifikowanego alarmu
`RiskyTemperatureForecast`. Wyniki mogą się różnić podczas potwierdzania
przekroczenia albo ustąpienia. Nieznany wynik lub brak danych do obliczenia
prognozy nie usuwa aktywnego alarmu; brak poprawnej prognozy oznacza brak
prognozowanej wartości, a nie zachowanie poprzedniej jako aktualnej.

Stan `healthy` encji `sensor.entity_health_temperature_forecast_<room>`
potwierdza kondycję wejścia, w tym dostępność i poprawność liczbową tempa zmian.
Nie oznacza, że prognozowana temperatura mieści się w granicach bezpieczeństwa.
Sprawne dane mogą wskazywać rzeczywiste ryzyko. Zadania naprawcze lub oceny
wykonania ścieżki **AppHealth** dotyczą działania aplikacji; ich brak nie
potwierdza braku zagrożenia temperaturą.

## Rozruch po restarcie

Po uruchomieniu lub restarcie backend zbiera i ocenia dane od razu, ale domyślnie
przez 10 minut wstrzymuje zgłaszanie części usterek diagnostycznych encji,
dostawców i utrzymania. Opóźnienie nie obejmuje kontroli czujników i łączności
z przypisanym budżetem wykrycia; zachowują one swoje terminy także podczas rozruchu.
W obu widokach na wszystkich stronach pozostaje widoczny komunikat
rozruchu z odliczaniem. Alarmy zagrożeń, w tym gaz, tlenek węgla i zalanie, oraz
błędy działania aplikacji są obsługiwane od razu.

Rozruch nie oznacza poprawnej oceny wszystkich funkcji. Odroczone wyniki mają
ocenę nieznaną (`UNEVALUABLE`), a niezależne poprawne wyniki nadal uczestniczą
w ocenie usterki. Brak aktywnych usterek nie jest potwierdzeniem pełnego
pokrycia. Po upływie czasu backend stosuje ostatnie nadal poprawne wyniki.
Niepoprawny lub utracony odczyt pozostaje nieznany i nie usuwa aktywnej usterki.

Sam upływ odliczania w przeglądarce nie kończy komunikatu: musi to potwierdzić
backend z aktualnymi, poprawnymi danymi. Brak połączenia oraz niepoprawne,
nieaktualne lub niedostępne przekazane dane rozruchu mają osobne oznaczenie.
Starszy backend bez danych rozruchu pozostaje obsługiwany; panel nie przypisuje
mu na tej podstawie fazy rozruchu.
Czas rozruchu można zmienić w konfiguracji monitora encji; wcześniejsza jawna
wartość jest zachowana, a `0` wyłącza to opóźnienie.

## Freeze frame

Przełącz widok na **Rozszerzony**, otwórz **Usterki i diagnostyka**, a potem
rozwiń kartę w sekcji **Zdarzenia i stan oceny**. Jedna sekcja **Freeze frame**
pokazuje zapis aktywacji, ostatnią przyczynę, liczniki, czasy i niepewność
pomiaru czasu z jednego obiektu
`freeze_frame` w atrybutach encji usterki (API/MQTT).

Dane przechwycone podczas aktywacji pozostają stałe; poprawne ustąpienie
uzupełnia czasy, a kolejna aktywacja zastępuje zapis i zwiększa licznik.
Po restarcie przerwanego pomiaru czas aktywności pozostaje nieznany. Brak
freeze frame nie oznacza ustąpienia usterki. Starszy backend z osobnymi
atrybutami jest prezentowany w tej samej sekcji.

## Pomoc w aplikacji

Pozycja **Pomoc** w nawigacji otwiera stronę `#/help`. Zawiera krótką instrukcję
korzystania z pulpitu, poziomy L1–L4 oraz rozwijane objaśnienia aktualności danych,
potwierdzeń powiadomień i działań, pomiarów oraz historii. Odnośniki prowadzą
do odpowiednich ekranów aplikacji. W widoku podstawowym pomoc jest w nagłówku;
w rozszerzonym także w menu telefonu.

Podpowiedzi przy ikonach **i** otwierają się po najechaniu myszą, dotknięciu
lub ustawieniu fokusu klawiaturą. Kliknięcie przypina podpowiedź; ponowne
kliknięcie, kliknięcie poza nią lub Escape zamyka ją. Oznaczenia braku połączenia
i ostatnich znanych danych pozostają widoczne przy odczytach.

## Historia powiadomień i encji

Na stronie **Historia** lista powiadomień znajduje się nad historią encji.
Pokazuje najnowsze próby przekazania powiadomień do Home Assistanta: aktywację
problemu (`SET`), jego aktualizacje i ponowienia, a także ustąpienie
(`CLEARED`). Usunięcie powiadomienia wskutek przesłonięcia problemu
(`SHADOWED`) jest osobnym zdarzeniem i nie oznacza, że problem ustąpił.

Każdy wpis pokazuje datę i godzinę w lokalnej strefie przeglądarki, etykietę
odbiorcy oraz wynik próby. Kliknij wpis, aby zobaczyć treść, poziom pilności,
czas utworzenia i próby, numer próby, informację o przekroczeniu terminu oraz
identyfikatory diagnostyczne. Przyjęcie przez Home Assistanta nie jest
potwierdzeniem dostarczenia na telefon. Dla grupy, np. `notify/all_phones`,
lista pokazuje etykietę grupy. Inne cele mają etykietę „Skonfigurowany
odbiorca”, a nazwę techniczną usługi można odczytać w szczegółach. Interfejs
nie ustala członków grup ani konkretnych osób, które otrzymały wiadomość.

Nazwa problemu w historii pochodzi z zapisanej wiadomości lub jej konkretnego
tytułu; starsze formaty powiadomień pozostają obsługiwane. Zmiana obecnej nazwy
urządzenia nie zmienia wcześniejszych wpisów. Sam myślnik w nazwie nie oznacza
lokalizacji. Jeśli lokalizacji nie zapisano, historia nie uzupełnia jej
dzisiejszym pomieszczeniem ani nie odgaduje jej z nazwy.

Dziennik pochodzi z `SafetyHomeApiGateway` przez uwierzytelnione zdarzenia
`safetyhome_notification_history_request` i
`safetyhome_notification_history_response`. Widok pobiera stronicowany,
spójny zestaw ostatnich 100 prób dla poszczególnych usług i wyświetla
najnowsze wpisy na początku. `sensor.notification_history` jest obsługiwany
wyłącznie jako zgodność ze starszą wersją backendu. Nieudana
próba i jej ponowienie mają osobne wpisy. Samo oczekiwanie na odzyskanie
Internetu nie jest próbą wysłania. Historia korzysta z istniejącego zapisu
stanu powiadomień i przy włączonej persystencji przetrwa restart AppDaemona;
wcześniejszy zapis bez dziennika rozpoczyna historię od pustej listy.
Rejestrator Home Assistanta nie jest wymagany do odczytu tej listy.
Historia encji pozostaje poniżej i korzysta z Rejestratora.
Zdarzenia transportu historii należy wyłączyć z Rejestratora; przykład do
scalenia z istniejącą konfiguracją znajduje się w
[`docs/examples/home_assistant_recorder_safetyhome_api.yaml`](../docs/examples/home_assistant_recorder_safetyhome_api.yaml).

### Utrata połączenia

Po utracie połączenia widok zachowuje ostatnie odczyty i wyraźnie oznacza je
jako dane zapamiętane. Taki odczyt nie potwierdza bieżącego bezpieczeństwa.
Potwierdzenie powiadomienia lub działania wymaga aktualnego połączenia.

### Potwierdzanie powiadomień

Rozwinięta karta aktywnej usterki poziomu L1–L3 na rozszerzonym pulpicie zawiera przycisk
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

Szczegółowa [instrukcja konfiguracji](CONFIGURATION.md) prowadzi przez pola i
działania w formularzu. YAML pozostaje opcją importu, a nie wymaganym sposobem
konfiguracji.

Podstrony konfiguracji zachowują jeden wspólny szkic. Reset instalacji ładuje
szablon tylko do formularza; wymaga osobnego zapisu i restartu. Nie kasuje
prywatnego pliku ani danych konserwacyjnych samym kliknięciem.

Widok zdrowia ma zwijalne grupy diagnostyczne z odczytami i czasami raportów.
Osobne, potwierdzane przyciski wysyłają mobilne powiadomienie testowe albo
resetują stare dane powiadomień i ponawiają nadal aktywne ostrzeżenia.
Wysyłka testu nie potwierdza jego odbioru, a reset nie kasuje alarmów.

Po pierwszym starcie aplikacji otwórz **Konfiguracja**. Panel pokaże szkic
`user_config.yml`; zastąp przykładowe encje i obszary danymi domu albo użyj
**Wczytaj user_config YAML**, aby wczytać istniejący plik `.yml`/`.yaml` w
modelu v2. Import tylko wypełnia formularz. Sprawdź go, zapisz i uruchom
ponownie aplikację, aby wystartował SafetyFunctions.

Strona edytuje włączone komponenty i providery, język, odbiorców powiadomień,
administracyjne dane lokalizacji, ustawienia komponentów oraz rejestry pomieszczeń,
otworów, detektorów i monitorowanych encji. `system_config.yml` jest częścią
wersjonowanego obrazu aplikacji. Cały panel Ingress jest dostępny tylko dla
administratorów Home Assistanta, ponieważ konfiguracja zawiera prywatną
topologię instalacji.

Szerokość i długość geograficzna są pobierane z Home Assistanta przy każdym
starcie i nie są zapisywane w `user_config.yml`. Horyzonty prognozy i domyślna
lista zagrożeń są dostarczane w `system_config.yml`. Dodatkowe monitorowane
encje wpisuje się osobno; zależności innych komponentów są monitorowane
automatycznie. Nazwy konkretnych encji można doprecyzować w prywatnych plikach
lokalizacji, poza `user_config.yml`.

Zapis jest przyjmowany tylko wtedy, gdy dokument nadal ma odczytaną rewizję,
przechodzi walidację modelu v2 i daje się skompilować z dołączoną konfiguracją
systemową. Po zapisie uruchom ponownie aplikację SafetyComponent. Dopiero
kontrolowany start tworzy nowe `apps.yaml` i wykonuje walidację zależną od
bieżących encji Home Assistanta.

## Działania rekomendowane

Karta działania pokazuje instrukcję, powód, źródło, ważność i bieżący etap
wykonania, a także oczekiwany wynik i przyczynę ewentualnej blokady. Te same
działania są widoczne przy powiązanej usterce i na liście działań.
Widok podstawowy pokazuje skrót instrukcji i jej bieżący status. Przycisk
**Wszystkie zalecenia** otwiera pełne karty z rezultatami, historią oraz
dostępnymi przyciskami zgłoszenia pracy i zgody na komendę.

Zamknięcie zwykłego okna lub drzwi jest czynnością ręczną. Dla zadań, które
dopuszczają zgłoszenie pracy, przycisk **Zgłoś wykonanie** wysyła informację
o zakończeniu czynności. Przy naprawie wymagającej obserwacji system czeka
na poprawny odczyt właściwego monitora. Przy zadaniu proceduralnym zgłoszenie
kończy tylko tę czynność; nie oznacza potwierdzenia usunięcia zagrożenia.
Zgłoszenie pracy nie kasuje usterki. Instrukcje doradcze nie mają przycisku
zgłoszenia ani potwierdzenia wykonania przez system.

Działanie zablokowane, w tym odtworzone po restarcie bez aktualnej oceny
monitora, zachowuje instrukcję i historię, ale nie udostępnia zgłoszenia pracy
ani zgody na komendę do czasu ponownej kwalifikacji.

Osobny przycisk zgody na komendę pojawia się dla skonfigurowanej bramy
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

Testy przeglądarkowe uruchamiają wyłącznie lokalny tryb demonstracyjny. Nie
wymagają konta ani tokenu Home Assistanta i blokują żądania do zewnętrznych
serwerów. Obejmują klawiaturę i fokus okien, ocenę bezpieczeństwa, utratę
połączenia, potwierdzenia powiadomień i działań oraz przełączanie historii na
widoku desktopowym i mobilnym:

```powershell
npx playwright install chromium
npm run test:ui
```

CI wykonuje testy, typecheck, lint bez ostrzeżeń, build i testy przeglądarkowe
przed budowaniem obrazu App. `npm run format:check` nadal sprawdza cały
frontend. Ponieważ istniejące pliki mają zastane różnice formatowania,
CI sprawdza TypeScript i JSON zmienione przez daną zmianę poleceniem
`npm run format:check:changed`. Ten zakres nie zwalnia zmienianych plików
z formatowania i pozwala zachować niezwiązane pliki bez masowego przepisywania.
Lokalnie porównanie domyślnie obejmuje zmiany względem `HEAD`; CI używa
commitu bazowego pull requesta lub poprzedniego commitu publikowanej zmiany.

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
