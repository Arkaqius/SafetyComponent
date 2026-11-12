export const configurationHelp: Array<{
  id: string;
  title: string;
  intro: string;
  entries: Array<{ title: string; text: string }>;
}> = [
  {
    id: 'general',
    title: 'Ogólne',
    intro: 'Wybierz funkcje i dostawców danych używanych w instalacji oraz język komunikatów SafetyComponent.',
    entries: [
      {
        title: 'Pierwsze uruchomienie',
        text: 'Uzupełnij formularz lub użyj „Wczytaj user_config YAML”. Wybierz rzeczywiste encje, uzupełnij wymagane pola i kliknij „Utwórz user_config.yml”. Dopiero restart aplikacji z poprawnie zapisanym plikiem uruchamia monitoring.',
      },
      {
        title: 'Wspólny szkic, zapis i restart',
        text: 'Wszystkie podstrony korzystają z jednego szkicu. „Zapisz konfigurację” sprawdza i zapisuje cały prywatny plik. Przed większą zmianą zachowaj kopię. „Uruchom ponownie aplikację” stosuje zapisane ustawienia i na krótko przerywa monitoring. Po restarcie sprawdź logi, stan usługi i pokrycie.',
      },
      {
        title: 'Import, odrzucanie i reset',
        text: 'Import YAML zastępuje szkic danymi z pliku. „Resetuj formularz do szablonu” zastępuje go publicznym wzorem i usuwa z formularza Twoje powiązania oraz nadpisania. Przed zapisem możesz wrócić do zapisanego pliku przyciskiem „Odrzuć zmiany”.',
      },
      {
        title: 'Komponenty',
        text: 'Włącz funkcję po przypisaniu źródeł, których potrzebuje. Po zmianie sprawdź „Zdrowie systemu”, ponieważ wyłączona lub nieoceniona kontrola wpływa na zakres monitorowania. Wejścia ogrzewania konfiguruje się w prywatnym YAML, w sekcji installation.heating_systems.',
      },
      {
        title: 'Providery API',
        text: 'Open-Meteo dostarcza dane pogodowe i jakość powietrza z dwóch niezależnych usług, a IMGW dostarcza oficjalne ostrzeżenia. Wybór wpływa na dostępne źródła oceny. Ich adresy i harmonogramy pochodzą z konfiguracji systemowej.',
      },
      {
        title: 'Język',
        text: 'Wybierz polski, angielski lub niemiecki dla komunikatów i nazw publikowanych przez SafetyComponent. Indywidualne nazwy encji mają oddzielny plik lokalizacji. Panel pomocy jest po polsku.',
      },
    ],
  },
  {
    id: 'notifications',
    title: 'Powiadomienia',
    intro: 'Wskaż usługi dostarczające komunikaty oraz opcjonalne urządzenia do sygnalizacji lokalnej.',
    entries: [
      {
        title: 'Adres po kliknięciu i odbiorcy',
        text: 'Wpisz ścieżkę otwieraną po dotknięciu powiadomienia, np. /. Każdą usługę notify/<nazwa> wpisz w osobnym wierszu i sprawdź jej odbiorcę w Home Assistant. Konkretny kanał daje możliwość sprawdzenia dostarczenia na docelowym urządzeniu.',
      },
      {
        title: 'Łączność WAN',
        text: 'Opcjonalna encja służy powiadomieniom i diagnostyce. Stany on, online i connected oznaczają dostępne połączenie, a off, offline i disconnected jego utratę. Dostępna łączność i odebranie komunikatu to dwa osobne wyniki.',
      },
      {
        title: 'Lokalne światło i alarm',
        text: 'Wskaż urządzenia przeznaczone do sygnalizacji bezpieczeństwa, jeżeli instalacja z nich korzysta. Przed użyciem sprawdź ich funkcję w konfiguracji Home Assistant. Wynik rzeczywistego odbioru powiadomień zapiszesz w „Zdrowie systemu → Testy i powiadomienia”.',
      },
    ],
  },
  {
    id: 'site',
    title: 'Instalacja HA',
    intro: 'Uzupełnij dane instalacji wykorzystywane do oceny warunków zewnętrznych oraz wskazań temperatury.',
    entries: [
      {
        title: 'Strefa czasowa, kraj i kody TERYT',
        text: 'Wybierz strefę czasową i wpisz dwuliterowy kod kraju. Kody powiatów TERYT do dopasowania ostrzeżeń IMGW wpisz po jednym w wierszu. Współrzędne są pobierane z ustawień Home Assistant przy każdym uruchomieniu aplikacji.',
      },
      {
        title: 'Temperatura zewnętrzna',
        text: 'Przy włączonym monitoringu temperatury wskaż encję rzeczywistego odczytu temperatury zewnętrznej. Wyszukaj ją po nazwie lub identyfikatorze i sprawdź, czy jest to właściwy czujnik w Twojej instalacji.',
      },
    ],
  },
  {
    id: 'health',
    title: 'Zdrowie systemu',
    intro: 'Podłącz źródła informacji o hoście, bateriach, kopiach i aktualizacjach. Brak źródła ogranicza zakres oceny.',
    entries: [
      {
        title: 'Pamięć i procesor hosta',
        text: 'Podaj razem encje dostępnej pamięci i jej presji PSI z tego samego hosta Home Assistant. Ocena pamięci łączy oba odczyty. Dla procesora wybierz opcjonalny odczyt procentowy CPU tego hosta. Czas potwierdzenia decyduje, czy skok obciążenia trwał wystarczająco długo, aby go zgłosić.',
      },
      {
        title: 'Wolne miejsce i temperatura hosta',
        text: 'Wybierz odczyt ilości wolnego miejsca w MiB, GiB lub bajtach oraz temperaturę hosta w °C. Są to dane urządzenia z Home Assistant. Procent zajętości dysku i temperatura pomieszczenia opisują inne wielkości.',
      },
      {
        title: 'Kopie zapasowe',
        text: 'Podaj czas ostatniej udanej kopii, aby oceniać jej wiek. Opcjonalny czujnik błędu kopii sygnalizuje błąd stanem on. Świeża kopia i potwierdzone odtworzenie to osobne wyniki.',
      },
      {
        title: 'Testy okresowe',
        text: 'Włącz potrzebne przypomnienia o sprawdzeniu odbioru powiadomień i odtworzeniu kopii na osobnym systemie testowym. W „Zdrowie systemu → Testy i powiadomienia” zapisuj wynik dopiero po rzeczywiście wykonanym teście. Włączenie przypomnienia ustala termin kontroli.',
      },
      {
        title: 'Aktualizacje',
        text: 'Przypisz opcjonalne encje update.* dla Home Assistant Core, OS, Supervisora i aplikacji SafetyComponent. Dostępna aktualizacja pojawia się jako ostrzeżenie L3. Ta karta służy do monitorowania dostępności aktualizacji.',
      },
      {
        title: 'Automatyczne wykrywanie baterii',
        text: 'Wykrywanie łączy procent baterii i binarny sygnał niskiego poziomu przypisane do tego samego urządzenia HA. Możesz wykluczyć wybrane urządzenia. Podgląd konfiguracji pomaga dobrać źródła, a ocenę działającego monitora znajdziesz po zastosowaniu zmian w „Zdrowie systemu → Baterie”.',
      },
      {
        title: 'Ręczne źródła baterii',
        text: 'Dodaj jeden wpis na urządzenie. Podaj czujnik procentowy z jednostką % lub sygnał niskiej baterii, w którym on oznacza niski poziom. Możesz podać oba odczyty z tego samego urządzenia. Wyłączenie wykrywania automatycznego zachowuje ręcznie skonfigurowane źródła.',
      },
    ],
  },
  {
    id: 'settings',
    title: 'Ustawienia komponentów',
    intro: 'Dopasuj progi i czasy do instalacji. Puste pola dziedziczą wartości systemowe, a ustawienia danego zasobu mają pierwszeństwo.',
    entries: [
      {
        title: 'Progi pamięci, CPU, dysku i temperatury',
        text: 'W sekcji „Functional Safety — progi i harmonogramy” ustaw oddzielne warunki zgłoszenia i powrotu. Przy powrocie wymagaj więcej wolnej pamięci i miejsca na dysku, niższej presji PSI oraz niższych wartości CPU i temperatury. Czasy potwierdzenia ograniczają reakcję na krótkie wahania.',
      },
      {
        title: 'WAN, baterie, kopie i terminy testów',
        text: 'Ustal czasy potwierdzenia utraty i powrotu WAN, próg niskiej baterii i maksymalny wiek kopii. Zmiana interwału testu przelicza termin od ostatniego zapisanego wyniku. „Przywróć domyślne ustawienia Functional Safety” usuwa te nadpisania ze szkicu.',
      },
      {
        title: 'Temperatura i czas otwarcia',
        text: 'Ustaw dolny i górny próg temperatury dla pomieszczeń bez własnych progów oraz domyślny czas alarmu otwarcia dla wejść bez własnego limitu. Czas otwarcia dotyczy widoku „Drzwi i bramy”. Ekspozycja na warunki zewnętrzne jest oceniana osobno.',
      },
      {
        title: 'Rozruch i czas potwierdzania usterek',
        text: 'Czas ochronny pozwala źródłom diagnostycznym ustabilizować się po starcie. Ocena zagrożeń i błędów aplikacji działa od początku. Maksymalny wiek raportu dotyczy świeżości źródła, a czas potwierdzenia awarii określa, jak długo problem ma się utrzymywać.',
      },
      {
        title: 'Wyjątki i dodatkowe monitorowane encje',
        text: 'Wyjątek dopasowuje diagnostykę encji, której używa już komponent. Dodatkowy wpis dodaje encję spoza tych zależności. Przykładowo dla czujnika raportującego rzadziej dobierz maksymalny wiek raportu do jego rzeczywistego rytmu publikacji.',
      },
      {
        title: 'Kontrole zdrowia encji',
        text: 'Wybierz stan encji lub konkretny atrybut. Sprawdzenie może dotyczyć obecności wartości, dopuszczalnych stanów, skończonej liczby, zakresu, tempa zmian lub aktualności. Dla aktualności wskaż wiarygodny znacznik czasu, a dla tempa zmian dobierz okno i liczbę próbek.',
      },
      {
        title: 'Pogoda i jakość powietrza',
        text: 'Dostosuj progi mrozu, porywów, opadów i wskaźnika AQI. Trwałość warunku pogodowego określa wymaganą długość warunku. Czas otwarcia drzwi i bram jest odrębną kwalifikacją, a lista domyślnych zagrożeń i horyzont prognozy pochodzą z konfiguracji systemowej.',
      },
    ],
  },
  {
    id: 'rooms',
    title: 'Pomieszczenia',
    intro: 'Przypisz pomieszczeniu obszar Home Assistant, czujnik temperatury oraz opcjonalne powiązania i progi.',
    entries: [
      {
        title: 'Dodanie i powiązanie pomieszczenia',
        text: 'Wpisz stabilny identyfikator, np. LivingRoom, kliknij „+ Dodaj obiekt” i rozwiń wpis. Wybierz obszar oraz encję pomiarową. Jeżeli chcesz powiązać okno, dodaj je wcześniej w „Drzwi i okna” i użyj identyfikatora tego wpisu. Osłona cover.* jest osobnym opcjonalnym polem.',
      },
      {
        title: 'Progi dla konkretnego pomieszczenia',
        text: 'Użyj „+ Dodaj pole”, aby wprowadzić własny dolny i górny próg, np. dla pomieszczenia o innych wymaganiach niż część mieszkalna. Własna wartość ma pierwszeństwo przed progiem instalacji. Po restarcie sprawdź odczyt oraz progi w widoku „Temperatury i trendy”.',
      },
    ],
  },
  {
    id: 'openings',
    title: 'Drzwi i okna',
    intro: 'Dodaj fizyczne okna, drzwi i bramy oraz wybierz, które kontrole mają je obejmować.',
    entries: [
      {
        title: 'Jeden wpis na fizyczny otwór',
        text: 'Podaj stabilny identyfikator, obszar, przyjazną nazwę, rodzaj otworu i encję położenia. Wybierz kontaktron lub właściwą encję cover.*. Stan zamknięcia opisuje położenie otworu. Stan zamka wymaga osobnego źródła.',
      },
      {
        title: 'Monitoring drzwi i bram',
        text: 'Dodaj tę rolę, gdy chcesz oceniać przekroczenie dozwolonego czasu otwarcia. Ustaw indywidualny limit albo użyj domyślnego limitu instalacji. Opcjonalny warunek monitorowania ma osobne stany zezwalające i blokujące. Sprawdź dokładne stany swojej encji warunku.',
      },
      {
        title: 'Zagrożenia zewnętrzne',
        text: 'Dodaj tę rolę, aby oceniać ekspozycję domu przy otwartym oknie, drzwiach lub bramie. Wybierz zagrożenia albo pozostaw wybór systemowy. Tryb ręczny daje wskazówkę. Tryb po potwierdzeniu wymaga właściwej osłony i jawnej zgody na konkretną propozycję.',
      },
    ],
  },
  {
    id: 'detectors',
    title: 'Detektory',
    intro: 'Powiąż czujniki dymu, gazu palnego, czadu i zalania z właściwym rodzajem zagrożenia oraz profilem odczytu.',
    entries: [
      {
        title: 'Dobór encji i profilu',
        text: 'Dodaj stabilny identyfikator, obszar, nazwę i encję alarmową binary_sensor.*. Wybierz rodzaj zagrożenia i profil odpowiadający znaczeniu stanów Twojego detektora. Dla gazu palnego podaj też rodzaj gazu.',
      },
      {
        title: 'Przykład czujnika zalania',
        text: 'Wybierz „Zalanie / wyciek wody”. Profil home_assistant_binary_alarm pasuje, gdy on oznacza wykrycie wody, a off stan suchy. Brak dostępnego odczytu pozostawia ocenę nieznaną. Po zastosowaniu konfiguracji sprawdź osobno alarm i stan techniczny w „Zagrożeniach wewnętrznych”.',
      },
    ],
  },
  {
    id: 'safety_routines',
    title: 'Scenariusze bezpieczeństwa',
    intro: 'Ułóż kontrole wykonywane przed snem, po wyjściu lub na żądanie. Scenariusze odczytują dane i zapisują raport.',
    entries: [
      {
        title: 'Utworzenie scenariusza i wybór sprawdzeń',
        text: 'Dodaj scenariusz i nadaj mu nazwę, np. „Przed snem”. Jest domyślnie wyłączony. Dodaj osobne sprawdzenie dla każdego odczytu, np. stan okna lub moc całego domu. Po sprawdzeniu źródeł włącz scenariusz, zapisz i zastosuj konfigurację.',
      },
      {
        title: 'Oczekiwane stany i zakres liczbowy',
        text: 'Dla stanu wpisz surową wartość z Home Assistant, np. off, jeżeli tak czujnik raportuje zamknięcie. Dla mocy wybierz źródło w W, podaj tę jednostkę i przynajmniej jedną granicę. Granice są włączne, więc maksimum 500 dopuszcza 500 W.',
      },
      {
        title: 'Czas obserwacji i warunek zastosowania',
        text: 'Kontrole standardowo wymagają czasu obserwacji i maksymalnego wieku. Przy oknie 0 s możesz wybrać ostatni znany odczyt encji, także dla kontroli mocy. Opcjonalny warunek zastosowania zawsze wymaga własnego czasu obserwacji.',
      },
      {
        title: 'Wyzwalacz, opóźnienie i próbki',
        text: 'Możesz użyć zdarzenia HA lub pełnej zmiany stanu, np. awake na asleep, jeżeli Twoje źródło publikuje te wartości. Opóźnienie dotyczy też „Sprawdź teraz”. Okno 0 s daje pojedynczą ocenę. Dłuższe okno zbiera próbki i zachowuje w raporcie stwierdzony problem lub lukę.',
      },
    ],
  },
];
