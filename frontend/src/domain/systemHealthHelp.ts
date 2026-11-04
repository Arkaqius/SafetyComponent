export const systemHealthHelp: Array<{ id: string; title: string; intro: string; entries: Array<{ title: string; text: string }> }> = [
  {
    id: 'health-entities',
    title: 'Monitorowane encje',
    intro: 'Sprawdź, które źródła dostarczają wiarygodne dane funkcjom bezpieczeństwa i co ogranicza ocenę konkretnego odczytu.',
    entries: [
      {
        title: 'Podsumowanie i lista źródeł',
        text: 'Liczniki obejmują encje nadzorowane przez SafetyComponent. „Sprawne” dotyczy jakości ich danych. „Wymagają uwagi” obejmuje także nieaktualne dane, a „Niedostępne” oznacza brak wymaganego odczytu. Na liście porównaj „Stan encji” z jej „Oceną”. Sprawny czujnik może prawidłowo zgłaszać alarm.',
      },
      {
        title: 'Jak znaleźć czujnik przypisany do funkcji?',
        text: 'Wpisz nazwę, identyfikator encji lub nazwę komponentu. Zawęź wyniki według oceny, pomieszczenia, właściciela albo pochodzenia. Właściciel to funkcja korzystająca z danych, a pochodzenie pokazuje, czy źródło wskazał użytkownik, czy wynika ono z monitoringu komponentu.',
      },
      {
        title: 'Szczegóły monitoringu i wyniki kontroli',
        text: 'Wybierz nazwę encji. Sprawdź ostatni poprawny odczyt, wynik każdej kontroli i podaną przyczynę. Dostępność, aktualność, wymagane wartości, zakres i tempo zmiany to osobne kontrole. „Potwierdzanie awarii” lub „Potwierdzanie powrotu” oznacza oczekiwanie na spełnienie kryteriów danej kontroli.',
      },
      {
        title: 'Czujnik wygląda na zamknięty, ale nie daje się ocenić',
        text: 'Porównaj bieżący stan z czasem ostatniego poprawnego odczytu i wynikiem kontroli aktualności. Czujnik może długo raportować tę samą wartość. Podgląd „Zmiany z ostatnich 24 godzin” pokazuje przejścia stanów, a wiarygodność sprawdzisz w wynikach kontroli. W zakładce „Usterki i pokrycie” zobaczysz, na jakie funkcje wpływa ten brak.',
      },
    ],
  },
  {
    id: 'health-batteries',
    title: 'Baterie',
    intro: 'Znajdź urządzenia z niską baterią lub brakiem wiarygodnej oceny i sprawdź odczyt oraz ostatni kontakt.',
    entries: [
      {
        title: 'Lista baterii i wyniki wyszukiwania',
        text: 'Wyszukaj urządzenie po nazwie lub encji. Wybierz filtr oceny i sortowanie. Domyślna kolejność pokazuje najpierw niskie baterie i brak oceny. Licznik wyników dotyczy wczytanych pozycji. Gdy pełna diagnostyka jest niedostępna, porównaj go z liczbą urządzeń objętych monitoringiem.',
      },
      {
        title: 'Co oznacza kreska zamiast procentu?',
        text: 'Ocena może pochodzić z flagi niskiej baterii albo z pomiaru procentowego. Kreska oznacza brak wiarygodnego procentu do wyświetlenia. „Brak oceny” może wynikać z braku świeżego kontaktu lub poprawnego odczytu. Ostatnia znana wartość nie potwierdza bieżącego poziomu.',
      },
      {
        title: 'Jak zweryfikować wymianę baterii?',
        text: 'Rozwiń urządzenie, a potem „Zaawansowaną diagnostykę baterii”. Sprawdź encję źródłową, ostatni kontakt i wartości, które zgłosiło urządzenie. Po wymianie poczekaj na świeży raport i sprawdź ocenę ponownie. Stan funkcji korzystającej z czujnika sprawdzisz osobno w „Usterkach i pokryciu”.',
      },
    ],
  },
  {
    id: 'health-platform',
    title: 'Platforma',
    intro: 'Sprawdź terminy ocen komponentów, stan hosta, kopie zapasowe, łączność WAN i dostępność aktualizacji.',
    entries: [
      {
        title: 'Postęp funkcji',
        text: 'Rozwiń kartę i odczytaj wynik oraz czas ostatniej oceny komponentu. „Ocena wykonana” potwierdza ukończenie logiki. Wiarygodność danych wejściowych sprawdzisz w „Monitorowanych encjach”, a możliwość oceny zagrożeń w „Usterkach i pokryciu”. Komponent zdarzeniowy może czekać na zdarzenie. Dla komponentu okresowego sprawdź termin i liczbę jego przekroczeń.',
      },
      {
        title: 'Host i kopie zapasowe',
        text: 'Porównaj ocenę dostępnej pamięci i jej przeciążenia (PSI), użycia procesora, wolnego miejsca i temperatury hosta. Gdy odczyt wymaga uwagi, rozwiń „Zaawansowaną diagnostykę źródła”, aby ustalić, skąd pochodzi wartość. W karcie kopii sprawdź datę ostatniej udanej kopii. Próbę odtworzenia dokumentuje osobny test okresowy.',
      },
      {
        title: 'Łączność WAN',
        text: 'Sprawdź, czy źródło zgłasza połączenie, utratę WAN lub brak wiarygodnych danych. W szczegółach odróżnij czas raportu encji od czasu oceny przez SafetyComponent. Oba czasy mogą być różne od momentu rzeczywistego testu łącza.',
      },
      {
        title: 'Aktualizacje',
        text: 'Rozwiń grupę i sprawdź, dla którego źródła dostępna jest aktualizacja. Brak wiarygodnych danych wymaga sprawdzenia źródła w Home Assistant. Karta pokazuje stan zgłoszony przez integrację, a aktualizację wykonuje się w Home Assistant.',
      },
      {
        title: 'Źródło danych i rozruch',
        text: 'Sprawdź, czy widzisz pełną diagnostykę backendu, czy skrócony stan encji Home Assistant. Po utracie połączenia panel może pokazywać poprzedni wynik. Podczas rozruchu część nowych usterek diagnostycznych czeka na zakończenie okresu kwalifikacji, a wykrywanie zagrożeń działa od razu.',
      },
    ],
  },
  {
    id: 'health-tests',
    title: 'Testy i powiadomienia',
    intro: 'Sprawdź próby wysyłki, terminy testów konserwacyjnych i zapisane wyniki rzeczywiście wykonanych prób.',
    entries: [
      {
        title: 'Powiadomienia i kolejka',
        text: '„Przyjęte przez HA” liczy wywołania zaakceptowane przez Home Assistant. „Nieudane próby” i „W kolejce” pokazują odpowiednio problemy wysyłki i żądania oczekujące. Szukając konkretnej próby, otwórz „Historię powiadomień”. Rzeczywisty odbiór potwierdź na urządzeniu odbiorcy.',
      },
      {
        title: 'Test fizyczny czujnika dymu, gazu lub czadu',
        text: 'Sprawdź termin przy konkretnym czujniku. Wykonaj fizyczny test zgodnie z instrukcją urządzenia i zapisz zaobserwowany wynik. Przyciski „Zapisz” rejestrują Twoje potwierdzenie. Po wysłaniu sprawdź, czy stan i data testu się zmieniły.',
      },
      {
        title: 'Test okresowy powiadomień',
        text: 'W „Testach okresowych” wybierz „Wyślij testowe powiadomienie”. Sprawdź rzeczywisty odbiór we wszystkich wymaganych kanałach, a potem zapisz wynik testu. Wysłanie żądania i zapis wyniku to dwa osobne kroki. Jeśli telefon nic nie odebrał, porównaj wynik w historii z tym, co zobaczyłeś na telefonie.',
      },
      {
        title: 'Test okresowy odtworzenia kopii',
        text: 'Odtwórz kopię wyłącznie na osobnym systemie testowym. Sprawdź odtworzone dane, a następnie zapisz wynik w „Testach okresowych”. Data ostatniego utworzenia kopii w zakładce „Platforma” to inna informacja niż potwierdzenie, że można ją odtworzyć.',
      },
      {
        title: 'Co usuwa reset powiadomień?',
        text: 'Reset usuwa zapisaną historię powiadomień, kolejkę, liczniki i potwierdzenia. To operacja nieodwracalna dla tej historii. Aktywne usterki zostaną ponownie zgłoszone. Wiadomości, które są już na telefonach, pozostają na urządzeniach.',
      },
    ],
  },
  {
    id: 'health-faults',
    title: 'Usterki i pokrycie',
    intro: 'Oddziel potwierdzone zagrożenia od problemów technicznych i ustal, które funkcje można nadal wiarygodnie ocenić.',
    entries: [
      {
        title: 'Aktywne zagrożenia, diagnostyka i informacje',
        text: 'Zagrożenie H dotyczy warunków w domu lub wokół niego, np. wykrytego dymu. Usterka diagnostyczna D może dotyczyć braku odczytu czujnika dymu albo problemu z usługą. Podsumowanie liczy aktywne warunki, a informacje L4 pokazuje osobno. Pełne pokrycie może występować podczas aktywnego zagrożenia.',
      },
      {
        title: 'Pokrycie bezpieczeństwa',
        text: '„Pełne” oznacza, że wymagane funkcje zostały ocenione. „Częściowe” wskazuje wyłączenia z zakresu, „zdegradowane” aktywne ograniczenia, a „nieustalone” brak rozstrzygającej oceny lub problem z powiązaniem źródła. Rozwiń „Co ogranicza monitorowanie”, aby sprawdzić wpływ na ocenę, powiadomienie, działanie naprawcze, publikację stanu lub zapis danych.',
      },
      {
        title: 'Jedno źródło i kilka powiązań',
        text: 'Rozwiń wiersz źródła, aby zobaczyć wszystkie opublikowane skutki i zakres każdego z nich. Przykładowo jeden brak odczytu okna ogranicza kilka ocen pogody. W „Zaawansowanej diagnostyce pokrycia” sprawdzisz także wyłączenia zakresu, błędy powiązań i funkcje bez rozstrzygającej oceny.',
      },
      {
        title: 'Zdarzenia i stan oceny',
        text: 'Użyj filtra „Wymagające uwagi”, aby zobaczyć także przypadki bez wiarygodnej oceny. Po rozwinięciu karty sprawdź aktywność, ocenę, lokalizację i źródła. „Potwierdzanie ustąpienia” oznacza oczekiwanie na dowód poprawy. Usterkę oznaczoną jako „Przesłonięta” odczytaj razem ze zdarzeniem nadrzędnym.',
      },
      {
        title: 'Podtrzymanie, potwierdzenie i zapis aktywacji',
        text: 'Alarm podtrzymany może pozostać widoczny po ustąpieniu warunku. „Potwierdź powiadomienie” zapisuje potwierdzenie wiadomości i nie usuwa alarmu. Gdy karta zawiera „Freeze frame”, odczytaj go jako zapis danych z chwili aktywacji. Bieżący stan i przebieg zmian sprawdzisz osobno w szczegółach encji.',
      },
    ],
  },
  {
    id: 'history',
    title: 'Historia',
    intro: 'Odtwórz kolejność zdarzeń, porównując próby wysyłki wiadomości z zapisanymi zmianami stanu systemu, usterek i działań.',
    entries: [
      {
        title: 'Jak znaleźć konkretną próbę wysyłki?',
        text: 'Na górze „Historii” zmień „Wynik wysyłki” na „Wszystkie próby” lub „Nieudane próby”. Możesz zawęzić listę według stanu usterki w chwili wysyłki. Rozwiń wpis, aby zobaczyć treść, rodzaj wiadomości, skonfigurowaną usługę odbiorcy, czas i numer próby. „Wysłano do HA” potwierdza przyjęcie wywołania, a odbiór sprawdza się na urządzeniu odbiorcy.',
      },
      {
        title: 'Jak odtworzyć przebieg usterki?',
        text: 'W „Historii stanów SafetyComponent” wybierz „Usterki” i zakres czasu, a w razie potrzeby przejdź do następnych encji. Porównaj czas i stan „Wtedy” z etykietą „Teraz”. Przy każdym wpisie usterki sprawdź zapisaną wtedy lokalizację i aktywację. Bieżąca lokalizacja widoczna u góry karty może się różnić.',
      },
      {
        title: 'Dlaczego są dwie historie?',
        text: 'Historia powiadomień rejestruje próby dostarczenia komunikatu do skonfigurowanej usługi. Historia stanów pochodzi z rejestratora Home Assistant i pokazuje zapisane przejścia encji. Jeśli lista jest pusta, sprawdź filtry i połączenie. Dla stanów sprawdź też zakres czasu oraz dostępność zapisu w rejestratorze.',
      },
      {
        title: 'Szczegóły i historia pojedynczej encji',
        text: 'Otwórz encję z karty, która udostępnia szczegóły. Ostatnia zmiana to czas zmiany stanu, a ostatnia aktualizacja może dotyczyć samych atrybutów. Pasek historii i lista pokazują przebieg wybranej encji w ustawionym zakresie. W „Zaawansowanej diagnostyce encji” znajdziesz jej techniczny identyfikator, surowe stany i opublikowane atrybuty.',
      },
    ],
  },
];
