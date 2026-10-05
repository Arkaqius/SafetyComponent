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
        <p>Znaczenie komunikatów, ograniczenia odczytów i różnica między potwierdzeniem powiadomienia a zgodą na działanie.</p>
      </section>

      <section className='help-quickstart' aria-labelledby='help-start'>
        <h3 id='help-start'>Od czego zacząć</h3>
        <ol>
          <li>
            Na <Link to='/'>pulpicie</Link> sprawdź bieżącą ocenę oraz informację o połączeniu i dostępności źródeł.
          </li>
          <li>Rozwiń aktywne zdarzenie, aby przeczytać jego opis, lokalizację i poziom pilności.</li>
          <li>Przeczytaj zalecenie i jego bieżący status. Potwierdź działanie dopiero po sprawdzeniu, czego dotyczy.</li>
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
          <Link className='text-link' to='/entities'>
            Sprawdź źródła danych <Icon name='chevron' size={16} />
          </Link>
        </section>

        <div className='help-topics'>
          <section aria-labelledby='help-statuses'>
            <h3 id='help-statuses'>Ocena i jakość danych</h3>
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
                Otwórz <Link to='/entities'>Encje i urządzenia</Link>, aby sprawdzić dostępne wyniki diagnostyki. Po odzyskaniu połączenia
                sprawdź, czy problem nadal jest zgłaszany.
              </p>
            </details>
            <details className='help-question'>
              <summary>Dlaczego usterka jest „Przesłonięta”?</summary>
              <p>
                Inne aktywne zdarzenie ma pierwszeństwo zgodnie z konfiguracją systemu. Przesłonięcie nie oznacza ustąpienia tej usterki. W
                sekcji zdarzeń użyj „Pokaż wszystkie”, aby zobaczyć pozostałe stany.
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
              <summary>Czy „Wysłane” w historii oznacza odbiór na telefonie?</summary>
              <p>
                Oznacza przyjęcie próby wysyłki przez Home Assistant. System nie potwierdza odbioru na telefonie. W{' '}
                <Link to='/history'>Historii</Link> rozwiń wpis, aby zobaczyć wynik próby i treść wiadomości.
              </p>
            </details>
          </section>

          <section aria-labelledby='help-readings'>
            <h3 id='help-readings'>Pomiary i historia</h3>
            <details className='help-question'>
              <summary>Jak czytać temperaturę i jej trend?</summary>
              <p>
                Temperatura to odczyt w °C. Zmiana w °C/min opisuje wzrost lub spadek na minutę; przyspieszenie w °C/min² opisuje zmianę
                tego tempa. Progi są skonfigurowane dla konkretnego źródła.
              </p>
              <p>
                Średnia obejmuje dostępne monitorowane odczyty. Nie zastępuje pomiaru w pomieszczeniu. Kliknij jej kartę na pulpicie albo
                otwórz <Link to='/temperature'>Temperatury</Link>, aby sprawdzić pomiary składowe.
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
              <summary>Skąd pochodzi jakość powietrza na pulpicie?</summary>
              <p>
                EAQI pochodzi z modelu Open-Meteo dla lokalizacji domu. Nie jest odczytem czujnika wewnątrz pomieszczenia. Nieaktualna
                wartość jest oznaczona jako ostatnia znana. Więcej informacji znajdziesz w{' '}
                <Link to='/external-hazards'>Zagrożeniach zewnętrznych</Link>.
              </p>
            </details>
          </section>

          <section aria-labelledby='help-interaction'>
            <h3 id='help-interaction'>Obsługa aplikacji</h3>
            <details className='help-question'>
              <summary>Jak otworzyć podpowiedzi i szczegóły?</summary>
              <p>
                Najedź myszą na „i”, dotknij tej ikony lub przejdź do niej klawiszem Tab. Kliknięcie przypina podpowiedź. Ponowne
                kliknięcie, dotknięcie poza nią lub Escape ją zamyka.
              </p>
              <p>
                Kliknij kartę z odczytem, aby otworzyć dostępne szczegóły. Okno zamkniesz przyciskiem zamknięcia lub Escape. Na telefonie
                nawigacja jest pod ikoną menu.
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
