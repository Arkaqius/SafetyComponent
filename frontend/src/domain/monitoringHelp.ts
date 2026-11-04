export const monitoringHelp = [
  {
    id: 'overview',
    route: '/',
    title: 'Przegląd',
    intro: 'Zacznij tutaj, gdy chcesz sprawdzić stan domu i ustalić, co wymaga Twojej uwagi.',
    entries: [
      {
        title: 'Bieżąca ocena domu',
        text: 'Przeczytaj stan, liczbę zdarzeń i lokalizację najpilniejszego z nich. „Ostatnia zmiana oceny” wskazuje zmianę zbiorczego stanu. Może pozostać starsza przy bieżących odczytach.',
      },
      {
        title: 'Podstawowy i rozszerzony',
        text: 'Widok podstawowy pokazuje skrót oceny, najpilniejsze zdarzenie, pokrycie i zalecenie. „Szczegóły i monitoring” lub „Wszystkie zdarzenia” otwierają widok rozszerzony. Wybór zapisuje się w tej przeglądarce.',
      },
      {
        title: 'Połączenie, rozruch i próbki',
        text: 'Przy braku połączenia czytaj widoczne wartości jako ostatnie znane dane. W rozruchu nowe usterki diagnostyczne czekają na stabilizację źródeł, a zagrożenia są oceniane od razu. Prognoza temperatury czeka osobno na próbki.',
      },
      {
        title: 'Skrót monitoringu i źródła danych',
        text: '„Oceny” prowadzą do postępu komponentów, „Pokrycie” do ograniczeń, „Wewnątrz” do detektorów, a „Otoczenie” do pogody i jakości powietrza. Licznik sprawnych źródeł obejmuje encje monitorowane przez SafetyComponent.',
      },
      {
        title: 'Zdarzenia i stan oceny',
        text: 'Rozwiń zdarzenie i sprawdź kategorię, poziom pilności, lokalizację, przyczyny oraz zalecenia. Zagrożenie H opisuje warunki w domu lub otoczeniu. Diagnostyka D opisuje sprawność czujnika, usługi lub kanału powiadomień.',
      },
      {
        title: 'Zalecenia i działania',
        text: 'Bieżąca lista pokazuje sprawy wymagające uwagi. Katalog zawiera także pozycje „Brak potrzeby”. Przeczytaj instrukcję, wykonawcę i powód wstrzymania. Zgoda na komendę, zgłoszenie pracy ręcznej i potwierdzenie powiadomienia to osobne czynności.',
      },
      {
        title: 'Średnia, najniższa i najwyższa temperatura',
        text: 'Karty podsumowują dostępne bieżące pomiary. Wybierz średnią, aby zobaczyć pomiary składowe, albo otwórz źródło wartości skrajnej. Minimum i maksimum z doby znajdziesz przy wykresie pomieszczenia.',
      },
      {
        title: 'Temperatura rośnie i ostatnie otwarcia',
        text: 'Pierwsza karta wskazuje źródło z największym raportowanym wzrostem. W „Ostatnich otwarciach” sprawdzisz niedawną zmianę położenia wejścia. Aktualny stan i limit otwarcia zobaczysz w „Drzwiach i bramach”.',
      },
    ],
  },
  {
    id: 'temperature',
    route: '/temperature',
    title: 'Temperatury',
    intro: 'Porównaj bieżące pomiary, trendy i prognozy przekroczenia granic w monitorowanych pomieszczeniach.',
    entries: [
      {
        title: 'Statystyki temperatury i karta pomieszczenia',
        text: 'Średnia i skrajne wartości dotyczą dostępnych bieżących pomiarów. Na karcie pomieszczenia sprawdź źródło i stan odczytu. Gdy dane są niedostępne, porównaj ich aktualność w szczegółach encji.',
      },
      {
        title: 'Trend, tempo i przyspieszenie',
        text: 'Trend podsumowuje kierunek zmian. Tempo pokazuje zmianę w °C/min, a przyspieszenie zmianę tego tempa. Oczekiwanie na próbki lub brak trendu oznacza, że kierunek może być jeszcze nieoceniony.',
      },
      {
        title: 'Wykres, zakres z historii i progi',
        text: 'Wykres obejmuje ostatnie 24 godziny. Zakres opisuje skrajne zapisane odczyty, a linie progów oznaczają skonfigurowane granice. Przy przerwie sprawdź historię i dostępność źródła przed interpretacją trendu.',
      },
      {
        title: 'Prognoza dolnej i górnej granicy',
        text: 'Sprawdź stan modelu, przewidywany wynik i próg. Prognoza zależy od jakości i liczby pomiarów. Bieżąca temperatura jest oceniana oddzielnie od prognozy.',
      },
    ],
  },
  {
    id: 'heating',
    route: '/heating',
    title: 'Ogrzewanie',
    intro: 'Sprawdź, jakie sygnały monitor ogrzewania widzi, jaką fazę rozpoznaje i które reguły może ocenić.',
    entries: [
      {
        title: 'System, faza pracy i pokrycie',
        text: 'Faza opisuje rozpoznany stan pracy instalacji. Pokrycie mówi o dostępnych ocenach. Przy niepełnej ocenie zacznij od tabeli „Wejścia”. Sam odczyt pracy urządzenia nie potwierdza dostarczenia ciepła do pomieszczeń.',
      },
      {
        title: 'Wejścia i jakość danych',
        text: 'Porównaj wielkość, źródło, odczyt i jego jakość. Jeżeli wartość budzi wątpliwości, sprawdź jednostkę i aktualność źródła w Home Assistant.',
      },
      {
        title: 'Zakres kontroli i szczegóły diagnostyczne',
        text: 'Każda reguła ma wynik i przyczynę. Wyłączona, nieoceniona i aktywna usterka mają różne znaczenia. Otwórz „Szczegóły diagnostyczne”, aby sprawdzić dane monitora.',
      },
    ],
  },
  {
    id: 'scenarios',
    route: '/safety-routines',
    title: 'Scenariusze bezpieczeństwa',
    intro: 'Uruchom odczyt wybranych źródeł przed snem lub wyjściem i sprawdź zapisany wynik.',
    entries: [
      {
        title: 'Scenariusze i odświeżanie',
        text: '„Odśwież” pobiera listę scenariuszy i ostatnich wykonań. Po zakończeniu pojawi się czas odczytu listy. Wyłączony scenariusz możesz sprawdzić w konfiguracji.',
      },
      {
        title: 'Sprawdź teraz, przebieg i anulowanie',
        text: 'Wybierz „Sprawdź teraz”, aby rozpocząć kontrolę z jej skonfigurowanym opóźnieniem. Przy aktywnym wykonaniu otwórz „Zobacz przebieg”. Jeżeli brak potwierdzenia, najpierw odśwież historię. Anulowanie zatrzymuje wskazane wykonanie.',
      },
      {
        title: 'Raport wykonania',
        text: 'Porównaj odczyt z oczekiwaniem i sprawdź czas obserwacji. „OK w chwili kontroli” dotyczy tego wykonania. „Nie można ocenić” wskazuje lukę w dowodach. Przy opóźnieniu, wielu próbkach lub przerwaniu sprawdź czasy etapów i status raportu.',
      },
      {
        title: 'Ostatnie wykonania',
        text: 'Lista pokazuje do 20 wykonań od najnowszego. „Pokaż raport” otwiera szczegóły wybranego wpisu. Na przykład po wyjściu porównaj czas kontroli z godziną zamknięcia okien. Starszy raport opisuje tamtą chwilę.',
      },
    ],
  },
  {
    id: 'doors',
    route: '/safety-doors',
    title: 'Drzwi i bramy',
    intro: 'Sprawdź stan monitorowanych wejść, warunki ich nadzoru i czas ciągłego otwarcia.',
    entries: [
      {
        title: 'Alarm aktywny, Otwarte i Dostępne',
        text: 'Alarm liczy wejścia z potwierdzonym przekroczeniem limitu. Otwarte obejmują też wejścia w czasie tolerancji. Dostępne wskazuje wejścia z czytelnym stanem.',
      },
      {
        title: 'Karta wejścia, limit i pozostały czas',
        text: 'Porównaj położenie, czas otwarcia, limit i „Pozostało”. Jeśli nadzór zależy od dodatkowego warunku, sprawdź jego stan. Brak wiarygodnego odczytu pozostawia położenie lub wynik nieustalone.',
      },
      {
        title: 'Alarm otwarcia a ekspozycja na pogodę',
        text: 'Przykład: drzwi mogą jeszcze mieścić się w swoim limicie otwarcia, a osobny monitor pogody może już zgłosić ekspozycję. Każda z tych kontroli ma własne warunki.',
      },
    ],
  },
  {
    id: 'internal',
    route: '/internal-hazards',
    title: 'Zagrożenia wewnętrzne',
    intro: 'Sprawdź alarmy domowych detektorów oraz dostępność ich kanałów alarmowych.',
    entries: [
      {
        title: 'Podsumowanie alarmów i detektorów',
        text: 'Porównaj aktywne alarmy, dostępne czujniki i liczbę niedostępnych źródeł. W razie alarmu otwórz kartę detektora i odczytaj jego lokalizację.',
      },
      {
        title: 'Alarm zagrożenia i stan techniczny',
        text: 'Alarm opisuje wykrycie warunku. Stan techniczny mówi, czy system ma wiarygodny odczyt alarmowy. Kontakt urządzenia może wynikać z raportu baterii i nie wystarcza do oceny alarmu.',
      },
      {
        title: 'Ochrona wyjść lokalnych',
        text: 'Przy detektorze gazu sprawdź, czy system sygnalizuje aktywną ochronę wyjść. Dotyczy ona skonfigurowanego zakresu lokalnych działań. Odczytaj równolegle stan alarmu i jego lokalizację.',
      },
      {
        title: 'Diagnostyka, encja źródłowa i stan monitorowania',
        text: 'Diagnostyka otwiera ocenę detektora, encja źródłowa pokazuje sygnał z Home Assistant, a stan monitorowania pozwala sprawdzić wiarygodność źródła. Zaawansowana diagnostyka zapisu pokazuje dane techniczne z chwili zdarzenia, jeśli są dostępne.',
      },
    ],
  },
  {
    id: 'external',
    route: '/external-hazards',
    title: 'Zagrożenia zewnętrzne',
    intro: 'Sprawdź warunki na zewnątrz, narażone wejścia i dostępność danych pogodowych.',
    entries: [
      {
        title: 'Warunki wymagające uwagi i narażone wejścia',
        text: 'Porównaj rodzaj warunku z listą dotkniętych wejść. Nowa ekspozycja przez drzwi lub bramę zwykle wymaga minuty ciągłego otwarcia. Otwarte okna i właściwe lokalne ostrzeżenia IMGW trzeciego stopnia są uwzględniane od razu.',
      },
      {
        title: 'Blokady porad otwarcia',
        text: 'Blokada wskazuje powód, dla którego system wstrzymuje poradę otwarcia. Sprawdź źródło i ważność. Ta karta opisuje spójność zaleceń.',
      },
      {
        title: 'Ostrzeżenia IMGW',
        text: 'Sprawdź treść, stopień, obszar i okres ważności komunikatu. Przy pustej liście porównaj stan integracji IMGW, aby odróżnić brak ostrzeżenia od problemu z pobraniem danych.',
      },
      {
        title: 'Stan niezależnych integracji i EAQI',
        text: 'Karta integracji pokazuje aktualność, zakres danych i błędy pobrania. EAQI z Open-Meteo opisuje modelowaną jakość powietrza na zewnątrz dla lokalizacji domu. Warunki wewnątrz wymagają pomiaru z pomieszczenia.',
      },
    ],
  },
];
