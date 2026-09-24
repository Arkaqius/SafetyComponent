# Konfiguracja w panelu Safety Home

Ten przewodnik prowadzi przez formularz **Safety Home → Konfiguracja** w Home
Assistant. Nie trzeba pisać YAML od zera. Panel zapisuje prywatny
`user_config.yml` aplikacji; polityka bezpieczeństwa i wartości systemowe są
dostarczane z aplikacją. Skrócony [szablon YAML](../backend/config/user_config.example.yml)
służy jako materiał techniczny. Pełny,
fikcyjny [przykład domu](../docs/examples/example_house_user_config.yml)
można obejrzeć lub wczytać do formularza.

## Pierwsze uruchomienie

1. Otwórz **Safety Home → Konfiguracja**. Przy świeżej instalacji panel pokaże
   informację o pierwszej konfiguracji. Możesz wypełnić formularz albo wybrać
   **Wczytaj user_config YAML**. Import tylko wypełnia formularz — nie zapisuje
   pliku bez Twojego potwierdzenia.
2. W Home Assistant sprawdź rzeczywiste identyfikatory w **Narzędzia
   deweloperskie → Stany** oraz identyfikatory obszarów w ustawieniach obszarów.
   Przykładowych identyfikatorów z dokumentacji nie kopiuj w ciemno.
3. Uzupełnij sekcje poniżej, potem kliknij **Utwórz user_config.yml** albo
   **Zapisz konfigurację**. Panel sprawdzi pola i zgodność z ustawieniami
   systemowymi. Zapis zastępuje dotychczasowy prywatny plik, więc przed większą
   zmianą zachowaj jego kopię.
4. Uruchom ponownie aplikację. Dopiero restart stosuje nową konfigurację i
   sprawdza dostępność encji. Sprawdź logi oraz stany czujników SafetyComponent.
   Nie uruchamiaj alarmów ani urządzeń wykonawczych tylko dla testu formularza.

## Przykład: mały dom

Fikcyjny dom ma salon, sypialnię, wejście, hol i pomieszczenie techniczne.
Poniższa kolejność odpowiada sekcjom formularza.
[Pełny plik przykładu](../docs/examples/example_house_user_config.yml) możesz
wczytać przez **Wczytaj user_config YAML**, aby obejrzeć wszystkie pola w GUI.
Sam import niczego nie zapisuje. Przed zapisem zastąp każde przykładowe
`entity_id`, `area_id`, usługę `notify/*` i kod TERYT wartościami z własnej
instalacji. Przykładowe progi nie są zaleceniem bezpieczeństwa.

1. W **Funkcjach i integracjach** włącz pięć komponentów domu. Wybierz język
   polski i rzeczywistą usługę powiadomień, np. własne `notify/mobile_app_*`.
2. W **Instalacji Home Assistant** wybierz `Europe/Warsaw`, kraj `PL`, własne
   czterocyfrowe kody powiatów TERYT oraz czujnik temperatury zewnętrznej.
   Nie wpisuj współrzędnych — aplikacja odczyta je z HA przy starcie.
3. W **Ustawieniach komponentów** przykład ustawia górny próg temperatury
   całego domu na `27 °C` i czas drzwi na `180 s`. Sypialnia ma własny próg
   `26 °C`, więc nadpisuje wartość całego domu. Brak nadpisania w salonie
   oznacza dziedziczenie `27 °C`.
4. W **Drzwiach, bramach i oknach** dodaj `LivingRoomWindow` z rolą
   **Zagrożenia zewnętrzne** oraz `EntranceDoor` z rolą **Monitoring drzwi i
   bram**. W **Pomieszczeniach** dodaj `LivingRoom` i `Bedroom`; salon
   odwołuje się do `LivingRoomWindow`. To jedno fizyczne okno, więc nie
   dodawaj drugiej kopii jego czujnika. Gdy nie ustawisz listy zagrożeń okna,
   dziedziczy ono systemowe zagrożenia domyślne.
5. W **Detektorach zagrożeń** dodaj `HallSmoke` z profilem
   `home_assistant_binary_alarm` z konfiguracji systemowej. Użyj go tylko,
   jeśli rzeczywista encja dymu raportuje stany zgodne z tym profilem.
6. W **Dodatkowych monitorowanych encjach** dodaj `UtilityHumidity` z
   kontrolami **Skończona liczba** i **Zakres liczbowy 0–100**. To dodatkowy
   czujnik, którego nie używa żaden z powyższych komponentów.

### Przykład wyjątku monitoringu encji

`EntranceDoor` jest już monitorowane jako zależność komponentu drzwi.
Nie dodawaj tej samej encji do **Dodatkowych monitorowanych encji**. Aby
zmienić jej kontrole, w **Wyjątkach monitoringu encji** dodaj klucz
`SafetyDoorEntranceDoor` (prefiks `SafetyDoor` i techniczny klucz otworu
`EntranceDoor`). Przykład ustawia opóźnienie wykrycia awarii na `10 s`, budżet
wykrycia na `30 s` i dozwolone stany na `on`/`off`. Te pola zmieniają sposób
oceny istniejącej zależności; **nie wyłączają jej monitorowania**. Nieznany
klucz wyjątku powoduje błąd przy starcie, a opóźnienie musi mieścić się w
budżecie wykrycia.

## Co wpisać w poszczególnych sekcjach

| Sekcja formularza | Co zrobić |
| --- | --- |
| Funkcje i integracje | Włącz tylko komponenty, dla których masz rzeczywiste źródła danych. Providery API można osobno włączać i wyłączać; ich adresy i harmonogramy są ustawieniami systemowymi. |
| Język | Wybierz polski, angielski lub niemiecki. Nazw encji nie edytuje się w tym formularzu — pochodzą z plików lokalizacji. |
| Powiadomienia | Wpisz konkretne usługi `notify/<nazwa>`, po jednej w wierszu. `notify/notify` jest niejednoznaczne. Adres po kliknięciu powinien być ścieżką w HA, np. `/`. Encja WAN i lokalne urządzenia sygnalizacji są opcjonalne. |
| Instalacja Home Assistant | Wybierz strefę czasową z listy, podaj dwuliterowy kod kraju, kody powiatów TERYT i — gdy komponent temperatury jest włączony — czujnik temperatury zewnętrznej. Współrzędne są pobierane z HA przy każdym starcie, nie wpisuje się ich w formularzu. |
| Ustawienia komponentów | Opcjonalnie zmień progi temperatury, czas drzwi/bram, czasy monitoringu lub progi pogody i jakości powietrza. Puste pole oznacza wartość systemową pokazaną pod polem. Lista domyślnych zagrożeń i horyzont prognozy pozostają w konfiguracji systemowej. |
| Pomieszczenia | Dodaj wpis dla każdego monitorowanego pomieszczenia. Wskaż obszar HA i czujnik temperatury. Opcjonalnie wybierz otwór z sekcji „Drzwi, bramy i okna”, osłonę `cover.*` i indywidualne progi. |
| Drzwi, bramy i okna | Każdy fizyczny otwór dodaj raz: obszar, encja czujnika, przyjazna nazwa i rodzaj. W razie potrzeby dodaj znane formularzowi role „Monitoring drzwi i bram” albo „Zagrożenia zewnętrzne” i wypełnij ich pola. Obecność roli włącza dany sposób monitorowania. |
| Detektory zagrożeń | Wskaż obszar, encję, nazwę, rodzaj zagrożenia i profil detektora z systemu. „Rodzaj gazu” jest wymagany tylko przy gazie palnym. |
| Dodatkowe monitorowane encje | Dodawaj wyłącznie encje, których nie używają inne komponenty. Ich zależności są monitorowane automatycznie. Wpisz encję i opis; opcjonalnie ustaw czasy i kontrole zdrowia. „Wyjątki monitoringu encji” obok dotyczą już istniejących zależności komponentów. |

## Dodawanie obiektów i kontrole zdrowia

W sekcjach zasobów wpisz **Nowy identyfikator**, np. `LivingRoom` albo
`EntranceDoor`, i kliknij **+ Dodaj obiekt**. Identyfikator jest techniczną,
stałą nazwą wpisu w formacie PascalCase, a nie tłumaczoną nazwą wyświetlaną.
Nowy wpis zawiera od razu wymagane pola właściwego typu. Rozwiń go, aby je
uzupełnić; wszystkie wpisy są początkowo zwinięte.

**+ Dodaj pole** pokazuje tylko pola dozwolone dla tego rodzaju obiektu.
Formularz nadaje im właściwe nazwy i typy: tekst, liczba, wybór, Tak/Nie lub
lista. Nie wpisuje się kluczy YAML ani JSON. Pola opcjonalne można usunąć
przyciskiem **Usuń ustawienie**. Na liście użyj **+ Dodaj element** i uzupełnij
każdy wiersz. Pole spoza znanego schematu jest oznaczone jako nieobsługiwane;
możesz je usunąć z formularza przed zapisem.

„Kontrole zdrowia” pozwalają dobrać aktualność danych, wymaganą wartość,
dozwolone stany, skończoną liczbę, zakres liczbowy i tempo zmian. Dodawaj
tylko kontrole, dla których znasz znaczenie stanu lub atrybutu encji. Przy
zakresie podaj co najmniej jedną granicę. Czasy kontroli muszą mieścić się w
budżecie wykrycia. Szczegółowe ograniczenia walidacji są w
[kontrakcie modelu](<../docs/features/Configuration Model - Architecture.md>).

## Wartości systemowe, nazwy i prywatność

Wartości domyślne i ich uzasadnienie opisuje
[konfiguracja systemowa](<../docs/reference/System Configuration.md>). Puste
ustawienie komponentu dziedziczy wartość systemową, a ustawienie pojedynczego
pomieszczenia lub otworu ma pierwszeństwo przed ustawieniem całej instalacji.
Usunięcie nadpisania może więc zmienić ocenę zagrożenia — sprawdź wynik po
zapisie i restarcie.

Nazwy ogólne są w publicznych plikach lokalizacji. Jeżeli potrzebujesz
prywatnej nazwy konkretnej encji, umieść ją poza `user_config.yml`, w pliku
`locales/pl.yml` w prywatnym katalogu konfiguracji aplikacji (odpowiednio
`en.yml` lub `de.yml` dla wybranego języka). Przykład zawartości:

```yaml
entity_name.sensor.safety_app_health: Stan bezpieczeństwa
```

Plik przyjmuje tylko wpisy `entity_name.<entity_id>: <nazwa>`. Nazwy prywatne
mają pierwszeństwo przed ogólnymi i są wczytywane po restarcie aplikacji.
Nie umieszczaj prawdziwego `user_config.yml` ani prywatnych plików lokalizacji
w publicznym repozytorium: mogą ujawniać topologię domu i odbiorców powiadomień.
