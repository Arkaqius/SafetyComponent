import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import StatusBadge from '../components/StatusBadge';
import { LEVEL_PRESENTATION } from '../domain/safety';
import { MOCK_MODE } from '../config';

export default function Help() {
  return (
    <div className='page-stack help-page'>
      <section className='help-introduction'>
        <h2>Jak korzystać z SafetyHome</h2>
        <p>Znajdź właściwy widok, odczytaj wynik kontroli i sprawdź, które działania wymagają Twojej uwagi.</p>
      </section>

      <section className='help-quickstart' aria-labelledby='help-start'>
        <h3 id='help-start'>Od czego zacząć</h3>
        <ol>
          <li>
            Zacznij od oceny domu i stanu połączenia w nagłówku. Przy aktywnym zdarzeniu odczytaj nazwę, lokalizację i pilność.{' '}
            <Link to='/'>Otwórz Przegląd</Link>.
          </li>
          <li>
            Widok podstawowy pokazuje najpilniejsze zdarzenie. Użyj „Szczegóły i monitoring” lub „Wszystkie zdarzenia”, aby zobaczyć
            pozostałe informacje.
          </li>
          <li>Przeczytaj zalecenie i sprawdź jego status oraz wykonawcę. Przed wysłaniem zgody przeczytaj nazwę i oczekiwany rezultat.</li>
          <li>
            Przy braku danych sprawdź ograniczoną funkcję, a następnie odszukaj jej źródło w diagnostyce.{' '}
            <Link to='/functional-safety?tab=faults'>Otwórz Usterki i pokrycie</Link>.
          </li>
        </ol>
      </section>

      <div className='help-layout'>
        <section className='help-reference' aria-labelledby='help-levels'>
          <h3 id='help-levels'>Poziomy pilności</h3>
          <p>Niższy numer oznacza wyższą pilność. Kolor zawsze ma opis tekstowy.</p>
          <dl className='help-levels'>
            {Object.entries(LEVEL_PRESENTATION).map(([level, presentation]) => (
              <div key={level}>
                <dt>{presentation.shortLabel}</dt>
                <dd>
                  <StatusBadge tone={presentation.tone}>{presentation.label}</StatusBadge>
                </dd>
              </div>
            ))}
          </dl>
          <p>„Brak alarmów” opisuje wynik dla monitorowanych źródeł. Sprawdź również aktualność i pokrycie monitoringu.</p>
          <Link className='text-link' to='/functional-safety'>
            Sprawdź źródła danych <Icon name='chevron' size={16} />
          </Link>
        </section>

        <div className='help-topics'>
          <section aria-labelledby='help-overview'>
            <h3 id='help-overview'>Przegląd domu</h3>
            <details className='help-question'>
              <summary>Jak czytać karty na pulpicie?</summary>
              <p>
                Zacznij od bieżącej oceny i najpilniejszego zdarzenia. W widoku rozszerzonym lista zdarzeń pokazuje poziom, lokalizację i
                status oceny, a sąsiednia lista grupuje zalecenia wymagające uwagi. Szczegóły zdarzenia pozwalają sprawdzić jego przyczyny i
                powiązane zalecenia.
              </p>
              <p>
                Licznik sprawnych źródeł dotyczy encji objętych diagnostyką. Karta zdrowia funkcji opisuje postęp ich ocen. Pokrycie
                bezpieczeństwa określa, które wymagane funkcje można ocenić i co ogranicza ich działanie.
              </p>
              <p>
                Karty temperatur pokazują średnią, skrajne odczyty i największy wzrost. Podsumowania zagrożeń prowadzą do detektorów,
                warunków zewnętrznych i ostrzeżeń. Ostatnie otwarcia prowadzą do monitorowanych drzwi i bram. Zwiń mniej potrzebne sekcje na
                pulpicie, aby szybciej wracać do bieżącego zdarzenia u góry. <Link to='/'>Otwórz Przegląd</Link>.
              </p>
            </details>
            <details className='help-question'>
              <summary>Jak rozpoznać aktualność stanu po utracie połączenia lub restarcie?</summary>
              <p>
                Stan połączenia w nagłówku dotyczy przeglądarki i Home Assistanta. „Ostatnia zmiana” przy odczycie oznacza moment zmiany
                konkretnego stanu. Na przykład zamknięty od wczoraj kontaktron może mieć starszą datę zmiany mimo bieżącego połączenia. Po
                utracie połączenia odczyty z etykietą „Ostatni znany stan” traktuj jako zapis z przeszłości.
              </p>
              <p>
                W rozruchu system zbiera dane i odkłada zgłaszanie nowych alarmów diagnostycznych. Ocenę zagrożeń wykonuje od razu.
                Zakończenie rozruchu potwierdza aplikacja. Prognozy temperatury mogą nadal czekać na własną historię pomiarów.{' '}
                <Link to='/functional-safety?tab=platform'>Sprawdź postęp funkcji</Link>.
              </p>
            </details>
          </section>

          <section aria-labelledby='help-routines'>
            <h3 id='help-routines'>Scenariusze bezpieczeństwa</h3>
            <p>
              <Link to='/safety-routines'>Uruchom kontrolę lub przeczytaj raport</Link> albo{' '}
              <Link to='/configuration/safety_routines'>skonfiguruj scenariusz</Link>.
            </p>
            <details className='help-question'>
              <summary>Jak sprawdzać dom po wyjściu lub przed snem?</summary>
              <p>
                W konfiguracji wybierz kontrole i pełną zmianę stanu. Dla instalacji z Home Monitor przykładowe wyzwalacze to
                sensor.home_monitor_occupancy: occupied → empty oraz sensor.home_monitor_activity: awake → asleep. Użyj surowego stanu
                asleep, nie sleep. Przykłady wymagają sprawdzenia encji w Twojej instalacji; nie są domyślnie włączone.
              </p>
              <p>
                Opóźnienie 120 s pozwala dokończyć wyjście lub rutynę wieczorną. Okno obserwacji 0 s oznacza jedną ocenę po opóźnieniu.
                „Sprawdź teraz” też stosuje opóźnienie. Restart nie uruchamia kontroli tylko dlatego, że dom jest już pusty lub śpi. Zmiana
                stanu podczas oczekiwania sama nie anuluje wykonania; dodaj także kontrolę obecności lub snu.
              </p>
            </details>
            <details className='help-question'>
              <summary>Gdzie sprawdzić, co wykazał scenariusz?</summary>
              <p>
                Wybierz „Pokaż raport” przy wykonaniu. Porównaj odczyt i oczekiwanie, a przy problemie lub luce przeczytaj wyjaśnienie i
                czas obserwacji. W historii znajdziesz ostatnie 20 wykonań. „OK w chwili kontroli” dotyczy czasu tego raportu.
              </p>
              <p>
                Jeśli ręczne uruchomienie nie otrzymało odpowiedzi, odśwież historię przed kolejną próbą. Kontrolę oczekującą lub trwającą
                możesz anulować w raporcie. Anulowanie i przerwanie po restarcie zachowują niepełny wynik.{' '}
                <Link to='/safety-routines'>Przejdź do scenariuszy</Link>.
              </p>
            </details>
            <details className='help-question'>
              <summary>Dlaczego przy zamkniętym oknie widzę „Nie można ocenić”?</summary>
              <p>
                Kontrola potrzebuje wartości i oryginalnego czasu jej obserwacji. Atrybut czasu musi rzeczywiście istnieć; samo wpisanie
                observed_at w formularzu go nie tworzy. Czas zmiany lub odczytania encji w HA i samo last_seen urządzenia nie dowodzą
                świeżości konkretnego pomiaru. Sprawdź wyjaśnienie w raporcie oraz źródło czasu i jego maksymalny wiek.
              </p>
              <p>
                „Nie można ocenić” oznacza brak dowodu. „Pominięte” oznacza znany warunek wyłączający kontrolę. Żaden z tych wyników nie
                jest OK. Raport zachowuje wykryte problemy i braki danych; wcześniejszy sukces dotyczy chwili kontroli.
              </p>
            </details>
            <details className='help-question'>
              <summary>Jak ustawić moc poniżej 500 W i kontrolę ogrzewania?</summary>
              <p>
                Wybierz czujnik mocy całego domu z jednostką W. Granice są włączne: maksimum 500 dopuszcza 500 W. Przykładowo przy
                rozdzielczości 0,1 W maksimum 499.9 i minimum 0 realizują limit poniżej 500 W. Licznik energii w kWh nie jest mocą.
              </p>
              <p>
                Sprawdź rzeczywisty tryb ogrzewania i jego surowe stany, np. away_short lub away_long. Nie zakładaj osobnego trybu sleep.
                Scenariusz nie zmienia trybu ani nastaw, nie steruje urządzeniami i nie kasuje usterek. Sam nie wysyła powiadomień; osobna
                automatyzacja może reagować na safety_routine_completed. Raporty znajdziesz w widoku scenariuszy.
              </p>
            </details>
          </section>
          <section aria-labelledby='help-statuses'>
            <h3 id='help-statuses'>Ocena i jakość danych</h3>
            <details className='help-question'>
              <summary>Czym różnią się zagrożenie, usterka diagnostyczna i pokrycie?</summary>
              <p>
                Zagrożenie (H) opisuje wykryty warunek, na przykład alarm dymu. Usterka diagnostyczna (D) opisuje problem techniczny, na
                przykład brak danych z czujnika lub niedostępność kanału powiadomień. Dym może zostać wykryty również podczas awarii
                wysyłki, jeśli detektor i ścieżka oceny działają.
              </p>
              <p>
                Pokrycie opisuje zakres możliwej oceny. Pełne pokrycie oznacza wykonanie wymaganych ocen, które mogą wykazać zagrożenie.
                Pokrycie częściowe wskazuje wyłączenia zakresu, zdegradowane oznacza znane ograniczenia techniczne, a nieustalone brak
                rozstrzygających danych. Rozwiń przyczynę, aby zobaczyć dotkniętą funkcję, urządzenie i rodzaj wpływu.{' '}
                <Link to='/functional-safety?tab=faults'>Otwórz Usterki i pokrycie</Link>.
              </p>
            </details>
            <details className='help-question'>
              <summary>Czy „Usługa działa” oznacza, że dom jest bezpieczny?</summary>
              <p>
                To informacja o działaniu SafetyComponent. Osobna ocena bezpieczeństwa uwzględnia stan systemu, usterki i dostępność danych.
                Sprawny czujnik może zgłaszać alarm.
              </p>
            </details>
            <details className='help-question'>
              <summary>Co oznaczają dane niepełne, nieaktualne lub brak połączenia?</summary>
              <p>
                System nie może potwierdzić pełnej bieżącej oceny. Przy utracie połączenia pozostają ostatnie znane wartości. Ich
                wcześniejszy poprawny stan nie potwierdza obecnego bezpieczeństwa.
              </p>
              <p>
                Otwórz <Link to='/functional-safety'>Zdrowie systemu</Link>, aby sprawdzić dostępne wyniki diagnostyki. Po odzyskaniu
                połączenia sprawdź, czy problem nadal jest zgłaszany.
              </p>
            </details>
            <details className='help-question'>
              <summary>Dlaczego usterka jest „Przesłonięta”?</summary>
              <p>
                Inne aktywne zdarzenie ma pierwszeństwo zgodnie z konfiguracją systemu. Przesłonięcie nie oznacza ustąpienia tej usterki. W
                sekcji zdarzeń użyj „Pokaż wszystkie”, aby zobaczyć pozostałe stany.
              </p>
            </details>
            <details className='help-question'>
              <summary>Gdzie znaleźć przyczynę techniczną?</summary>
              <p>
                Zacznij od zakładki „Usterki i pokrycie”. Filtr „Wymagające uwagi” uwzględnia również nieocenione i niewiarygodne stany.
                Rozwiń wpis, sprawdź dowody oceny i powiązane działanie. Przy alarmie podtrzymanym sprawdź osobno stan warunku i informację
                o podtrzymaniu. W szczegółach technicznych znajdziesz zapis danych z chwili zdarzenia (Freeze frame), jeśli jest dostępny.
              </p>
              <p>
                Jeśli przyczyną jest brak odczytu, wyszukaj jego źródło w zakładce „Monitorowane encje”. Szczegóły wiersza pokazują wynik
                poszczególnych kontroli, przyczynę i dostępne czasy. Lista obejmuje źródła przypisane do diagnostyki SafetyComponent.{' '}
                <Link to='/functional-safety?tab=entities'>Otwórz Monitorowane encje</Link>.
              </p>
            </details>
          </section>

          <section aria-labelledby='help-health'>
            <h3 id='help-health'>Zdrowie systemu</h3>
            <details className='help-question'>
              <summary>W której zakładce szukać informacji?</summary>
              <p>
                <strong>Usterki i pokrycie</strong> gromadzi zdarzenia, stan ocen oraz wpływ diagnostyki na poszczególne funkcje.{' '}
                <strong>Monitorowane encje</strong> pozwalają znaleźć problematyczne źródło po nazwie, ocenie lub obszarze.{' '}
                <strong>Baterie</strong> grupują obsługę urządzeń bateryjnych. Rozwiń wiersz baterii, aby odróżnić procent, jakość źródła i
                ostatni kontakt. Brak wiarygodnego procentu jest osobną oceną.
              </p>
              <p>
                <strong>Platforma</strong> pokazuje postęp ocen komponentów oraz stan skonfigurowanych źródeł hosta i konserwacji, takich
                jak miejsce na dysku, kopie zapasowe i aktualizacje. <strong>Testy i powiadomienia</strong> zawierają stan wysyłki, kolejkę,
                terminy oraz zapisane wyniki testów. <Link to='/functional-safety'>Otwórz Zdrowie systemu</Link>.
              </p>
            </details>
            <details className='help-question'>
              <summary>Jak sprawdzić powiadomienia i zapisać wynik testu?</summary>
              <p>
                W sekcji testów sprawdź, czego dotyczy termin. Po fizycznym teście detektora zapisz jego rzeczywisty wynik. Przy teście
                powiadomień sprawdź odbiór we wszystkich wymaganych kanałach. Przy teście kopii sprawdź odtworzone dane na osobnym systemie
                testowym. Zapis wyniku jest oświadczeniem operatora, a wysłanie próbnego powiadomienia to osobna czynność.
              </p>
              <p>
                Gdy wiadomość nie dotarła, porównaj stan kolejki i ostatnie próby wysyłki. Szczegóły próby znajdziesz w Historii.{' '}
                <Link to='/functional-safety?tab=tests'>Otwórz Testy i powiadomienia</Link>.
              </p>
            </details>
          </section>

          <section aria-labelledby='help-confirmations'>
            <h3 id='help-confirmations'>Powiadomienia i działania</h3>
            <details className='help-question'>
              <summary>Co robi „Potwierdź powiadomienie”?</summary>
              <p>
                Przekazuje informację, że przyjąłeś powiadomienie do wiadomości, i zatrzymuje jego dalsze powtórzenia. Nie usuwa usterki,
                nie naprawia czujnika ani nie wykonuje zalecanego działania.
              </p>
            </details>
            <details className='help-question'>
              <summary>Czy potwierdzone działanie zostało już wykonane?</summary>
              <p>
                Potwierdzenie wysyła zgodę do systemu. Sprawdź późniejszy status działania; wysłanie zgody nie jest potwierdzeniem
                wykonania. Propozycja może wygasnąć lub przestać spełniać warunki wykonania.
              </p>
              <p>
                Zalecenia dotyczące zwykłych okien i drzwi wykonujesz ręcznie. Przed zgodą na ruch bramy upewnij się, że może zostać
                wykonany bezpiecznie.
              </p>
            </details>
            <details className='help-question'>
              <summary>Co oznacza nieaktywne zalecenie lub „Brak potrzeby”?</summary>
              <p>
                „Brak potrzeby” w katalogu oznacza, że system nie wymaga obecnie wykonania tej czynności. Katalog pokazuje także znane,
                nieaktywne pozycje. Do codziennej pracy użyj listy zaleceń wymagających uwagi. Jeżeli w szczegółach widzisz ostatni wynik i
                datę, czytaj je jako historię danego działania.
              </p>
              <p>
                „Wstrzymane” oznacza, że propozycja jest zablokowana lub wygasła. Przeczytaj powód. „W trakcie” oznacza oczekiwanie na
                wynik. „Potwierdzone” opisuje wynik dla danego działania i jego warunku ukończenia. Przy pracy ręcznej „Zgłoś wykonanie”
                zapisuje Twoje zgłoszenie, a gdy system wymaga odczytu urządzenia, nadal czeka na dowód rezultatu.{' '}
                <Link to='/'>Otwórz Zalecenia i działania na pulpicie</Link>.
              </p>
            </details>
            <details className='help-question'>
              <summary>Czy „Wysłane” w historii oznacza odbiór na telefonie?</summary>
              <p>
                Oznacza przyjęcie próby wysyłki przez Home Assistant. System nie potwierdza odbioru na telefonie. W{' '}
                <Link to='/history'>Historii</Link> rozwiń wpis, aby zobaczyć wynik próby i treść wiadomości.
              </p>
            </details>
          </section>

          <section aria-labelledby='help-hazards'>
            <h3 id='help-hazards'>Drzwi, bramy i zagrożenia</h3>
            <details className='help-question'>
              <summary>Dlaczego otwarte drzwi jeszcze nie wywołały alarmu?</summary>
              <p>
                Na karcie drzwi lub bramy porównaj czas otwarcia, limit i pole „Pozostało”. Przy odliczaniu monitoring czeka na
                przekroczenie limitu ciągłego otwarcia. Gdy widzisz „Wstrzymane”, sprawdź warunek monitorowania, ponieważ w tym stanie
                system nie odlicza limitu. „Brak danych” oznacza, że aktualnego położenia nie udało się potwierdzić.{' '}
                <Link to='/safety-doors'>Otwórz Drzwi i bramy</Link>.
              </p>
            </details>
            <details className='help-question'>
              <summary>Jak czytać kartę detektora?</summary>
              <p>
                Odczytaj „Alarm zagrożenia”, „Stan techniczny” i lokalizację. „Ostatni kontakt urządzenia” może oznaczać raport baterii lub
                inną wiadomość. Stan alarmowy może być niedostępny mimo świeżego kontaktu. Przy gazie karta pokazuje także stan ochrony
                wyjść lokalnych. Użyj przycisku „Diagnostyka” lub „Encja źródłowa”, aby zobaczyć szczegóły.{' '}
                <Link to='/internal-hazards'>Otwórz Zagrożenia wewnętrzne</Link>.
              </p>
            </details>
            <details className='help-question'>
              <summary>Gdzie sprawdzić pogodę, ostrzeżenia IMGW i narażone wejścia?</summary>
              <p>
                W widoku zagrożeń zewnętrznych sprawdź warunki wymagające uwagi, narażone okna, drzwi lub bramy oraz blokady porad otwarcia.
                Karta ostrzeżenia IMGW pokazuje jego treść i zasięg. Przy braku aktualnej oceny sprawdź stan każdego źródła, czas odczytu i
                błędy pobierania. <Link to='/external-hazards'>Otwórz Zagrożenia zewnętrzne</Link>.
              </p>
              <p>
                Nowe zgłoszenie ekspozycji na pogodę lub zanieczyszczone powietrze przy drzwiach lub bramie wymaga minuty ciągłego otwarcia.
                Otwarte okna oraz lokalne ostrzeżenie IMGW trzeciego stopnia dla danego zagrożenia są uwzględniane od razu. Limit otwarcia
                widoczny w „Drzwiach i bramach” dotyczy osobnej kontroli.
              </p>
              <p>
                EAQI na pulpicie pochodzi z modelu Open-Meteo dla lokalizacji domu. Do oceny powietrza wewnątrz potrzebujesz odpowiedniego
                pomiaru z pomieszczenia.
              </p>
            </details>
          </section>

          <section aria-labelledby='help-readings'>
            <h3 id='help-readings'>Temperatury, ogrzewanie i historia</h3>
            <details className='help-question'>
              <summary>Jak czytać temperaturę i jej trend?</summary>
              <p>
                Temperatura to odczyt w °C. Zmiana w °C/min opisuje wzrost lub spadek na minutę; przyspieszenie w °C/min² opisuje zmianę
                tego tempa. Progi są skonfigurowane dla konkretnego źródła.
              </p>
              <p>
                Średnia obejmuje dostępne monitorowane odczyty. Wybierz konkretne pomieszczenie, aby zobaczyć wykres z ostatnich 24 godzin i
                porównać odczyt z jego progami. Przy prognozie sprawdź horyzont, czas oceny i gotowość próbek. Wynik prognozy i potwierdzony
                alarm mają osobne statusy. <Link to='/temperature'>Otwórz Temperatury</Link>.
              </p>
            </details>
            <details className='help-question'>
              <summary>Dlaczego wykres jest pusty lub ma przerwy?</summary>
              <p>
                Historia wymaga dostępnych próbek z Rejestratora Home Assistanta. Źródło mogło nie być zapisywane, mieć zbyt mało próbek lub
                być niedostępne. Błąd pobrania i brak połączenia mają osobne komunikaty.
              </p>
              <p>
                Brak historii nie oznacza stałego odczytu. Minima i maksima obejmują dostępne próbki, więc luki mogą ukrywać skrajne
                wartości.
              </p>
            </details>
            <details className='help-question'>
              <summary>Co sprawdza nadzór ogrzewania?</summary>
              <p>
                „Wejścia” pokazują wartości, źródła i jakość danych. „Zakres kontroli” pokazuje włączone reguły i wyjaśnienia. Zacznij od
                zakresu, gdy widzisz częściowe pokrycie. Jeżeli działa tylko R01, pozytywny wynik potwierdza dostępność i poprawność
                wymaganych odczytów. Kontrole pracy kotła i dostarczania ciepła mają własne wyniki po włączeniu odpowiednich reguł.{' '}
                <Link to='/heating'>Otwórz Ogrzewanie</Link>.
              </p>
            </details>
            <details className='help-question'>
              <summary>Jak odtworzyć kolejność zdarzeń?</summary>
              <p>
                W Historii wybierz kategorię „System”, „Usterki” lub „Działania” i zakres czasu. Rozwiń encję, aby porównać jej zmiany stanu
                z czasem zdarzenia. W historii powiadomień sprawdzisz osobno próby wysyłki, treść i potwierdzenia. Raporty kontroli po
                wyjściu i przed snem są dostępne w historii wykonań scenariuszy. <Link to='/history'>Otwórz Historię</Link>.
              </p>
            </details>
          </section>

          <section aria-labelledby='help-configuration'>
            <h3 id='help-configuration'>Konfiguracja instalacji</h3>
            <details className='help-question'>
              <summary>Jak zmienić encję lub próg i zastosować zmianę?</summary>
              <p>
                Wybierz podstronę konfiguracji. „Ogólne” zawiera język i wybór funkcji, „Powiadomienia” ich adresatów, a „Instalacja HA”
                ustawienia lokalizacji. Progi i czasy zmienisz w „Ustawieniach komponentów”. Pomieszczenia, drzwi i okna, detektory oraz
                scenariusze mają osobne formularze. Ustawienia źródeł technicznych są w podstronie „Zdrowie systemu”.
              </p>
              <p>
                Wyszukaj właściwą encję, sprawdź jednostkę lub surowe stany i zapisz cały szkic. Import YAML oraz reset do szablonu najpierw
                zmieniają szkic. Po sprawdzeniu zapisanego pliku użyj „Uruchom ponownie aplikację”, aby wczytać ustawienia. Polecenie wymaga
                odpowiednich uprawnień i restartuje SafetyComponent. <Link to='/configuration'>Otwórz Konfigurację</Link>.
              </p>
            </details>
          </section>

          <section aria-labelledby='help-interaction'>
            <h3 id='help-interaction'>Obsługa aplikacji</h3>
            <details className='help-question'>
              <summary>Czym różnią się widoki podstawowy i rozszerzony?</summary>
              <p>
                Podstawowy pokazuje ocenę domu, najpilniejsze aktywne zdarzenie, zalecenie i ograniczenia monitoringu. Rozszerzony
                udostępnia wszystkie zdarzenia, pomiary, historię, diagnostykę i konfigurację. Dłuższe instrukcje pozostają widoczne w
                całości i mogą wymagać przewinięcia.
              </p>
              <p>
                Zmień widok przełącznikiem w nagłówku. Wybór jest zapamiętany tylko w tej przeglądarce. Odnośnik do szczegółowej podstrony
                otwiera widok rozszerzony; „Podstawowy” prowadzi z powrotem na pulpit.
              </p>
            </details>
            <details className='help-question'>
              <summary>Jak otworzyć podpowiedzi i szczegóły?</summary>
              <p>
                Najedź myszą na „i”, dotknij tej ikony lub przejdź do niej klawiszem Tab. Kliknięcie przypina podpowiedź. Ponowne
                kliknięcie, dotknięcie poza nią lub Escape ją zamyka.
              </p>
              <p>
                Ikona „i” wyświetla objaśnienie. Jeśli karta ma przycisk szczegółów, użyj go, aby otworzyć odczyty i historię. Okno
                zamkniesz przyciskiem zamknięcia lub Escape. Na telefonie przejdź do widoku rozszerzonego, a potem użyj „Otwórz nawigację”.
              </p>
            </details>
          </section>
          {MOCK_MODE && (
            <aside className='help-demo-note' aria-label='Tryb demonstracyjny'>
              <strong>Tryb demonstracyjny</strong>
              <p>
                Ten podgląd korzysta z lokalnych danych testowych. Odczyty i działania nie dotyczą rzeczywistego domu. Produkcyjna aplikacja
                pobiera dane z Home Assistanta.
              </p>
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}
