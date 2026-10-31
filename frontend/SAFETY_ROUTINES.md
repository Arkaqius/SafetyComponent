# Scenariusze bezpieczeństwa

Scenariusz zbiera raport z wybranych kontroli przed snem lub po wyjściu z domu.
Otwórz **Scenariusze bezpieczeństwa**, wybierz **Sprawdź teraz**, a następnie
**Pokaż raport** przy wykonaniu. Przycisk respektuje skonfigurowane opóźnienie.
Scenariusz odczytuje dane: nie zmienia nastaw pieca ani ogrzewania, nie zamyka
bram i nie wyłącza urządzeń. Sam nie wysyła powiadomień na telefon.

## Poza domem i przed snem

Poniższe ustawienia są przykładami dla instalacji z Home Monitor. Nie są
wbudowanymi regułami ani domyślnie włączonymi scenariuszami. Sprawdź identyfikatory
i surowe stany w swojej instalacji; nazwa widoczna w HA może być przetłumaczona.

| Ustawienie | Poza domem | Przed snem |
| --- | --- | --- |
| Rodzaj wyzwalacza | Zmiana stanu | Zmiana stanu |
| Encja wyzwalacza | `sensor.home_monitor_occupancy` | `sensor.home_monitor_activity` |
| Stan początkowy | `occupied` | `awake` |
| Stan docelowy | `empty` | `asleep` — nie `sleep` |
| Przykładowe opóźnienie | 120 s na dokończenie wyjścia | 120 s na dokończenie rutyny wieczornej |
| Okno obserwacji | 0 s: jedna ocena po opóźnieniu | 0 s: jedna ocena po opóźnieniu |
| Kontrole | Pusty dom, zamknięte wybrane otwory, moc całego domu, właściwy tryb ogrzewania | Stan snu, zamknięte wybrane otwory, moc całego domu |

Przejście musi wystąpić po uruchomieniu SafetyComponent. Jeśli dom jest już
pusty lub domownicy już śpią, restart nie uruchomi kontroli ponownie. Możesz użyć
**Sprawdź teraz**. Zmiana stanu podczas opóźnienia nie anuluje automatycznie
wykonania; dodaj kontrolę bieżącej obecności lub snu, aby raport ją uwzględniał.

Tryb ogrzewania odczytaj z encji, która rzeczywiście go opisuje. W instalacji
publikującej `away_short` i `away_long` można wskazać oba jako oczekiwane stany.
Nie zakładaj istnienia trybu `sleep`. Stan palnika i tryb ogrzewania to różne
informacje; żadna z tych kontroli nie wysyła poleceń do ogrzewania.

## Dodanie kontroli w formularzu

1. Otwórz **Konfiguracja → Scenariusze bezpieczeństwa**. Dodaj nazwany scenariusz;
   nowy wpis jest wyłączony.
2. Dla każdego wybranego okna, drzwi lub bramy dodaj oddzielną kontrolę stanu.
   Wybierz rzeczywistą encję oraz jej surowy stan zamknięcia, np. `off` dla
   kontaktronu albo `closed` dla osłony. Zamknięte drzwi nie dowodzą zaryglowania.
3. Dla mocy wybierz **Zakres liczbowy**, czujnik mocy całego domu i jednostkę `W`.
   Nie używaj licznika energii w `kWh` ani czujnika jednego urządzenia jako mocy
   całego domu. Minimum i maksimum są włączne: maksimum `500` dopuszcza 500 W.
   Dla przykładowego wymagania „poniżej 500 W” przy rozdzielczości 0,1 W wybierz
   maksimum `499.9` i minimum `0`. Dobierz limit do instalacji.
4. Każdej kontroli przypisz dokładnie jedno źródło oryginalnego czasu obserwacji:
   encję, której stan jest tym czasem, albo rzeczywisty atrybut czasu na encji
   wartości. Obsługiwany jest ISO 8601 ze strefą lub liczbowy Unix w sekundach.
   `last_changed`, `last_updated`, czas odebrania wiadomości i samo `last_seen`
   urządzenia nie dowodzą czasu pomiaru konkretnej wartości.
5. Ustaw maksymalny wiek obserwacji zgodnie z częstotliwością pomiarów źródła.
   Wpisanie nazwy `observed_at` w formularzu nie tworzy takiego atrybutu.
   Jeżeli źródło nie dostarcza wymaganego czasu, kontrola pozostanie nieoceniona;
   sam poprawnie zapisany formularz nie potwierdza gotowości danych.
6. Dodaj wyzwalacz i opóźnienie. Opcjonalne okno obserwacji większe od zera
   pobiera próbki co 5 s i na końcu okna. Kolejne pozytywne próbki wymagają
   nowych obserwacji źródła. Wykryty problem lub luka nie znika po późniejszej
   pozytywnej próbce. Okno nie dowodzi stanu między próbkami.
7. Włącz scenariusz, zapisz konfigurację i zastosuj ją przez restart aplikacji.
   Zachowaj kopię prywatnej konfiguracji. Sprawdź stan aplikacji i logi zgodnie
   z [procedurą konfiguracji](CONFIGURATION.md#pierwsze-uruchomienie).

Wybrane otwory są oddzielnymi wpisami scenariusza. Dodanie nowego okna do
rejestru instalacji nie dodaje automatycznie kontroli do istniejących scenariuszy.

## Jak czytać raport

| Wynik | Co oznacza | Co zrobić |
| --- | --- | --- |
| OK | Świeża, zakwalifikowana obserwacja spełniła oczekiwanie. | Sprawdź czas raportu; wynik jest historyczny. |
| Problem | Zakwalifikowana obserwacja naruszyła oczekiwanie. | Sprawdź wskazane źródło i sytuację w domu. |
| Nie można ocenić | Brakuje wartości, wiarygodnego czasu, właściwej jednostki lub znanego warunku. | Odczytaj wyjaśnienie; sprawdź źródło i jego powiązanie. |
| Pominięte | Znany, świeży warunek wybrał skonfigurowany stan pomijania. | Sprawdź, czy wyłączenie ma zastosowanie. |

„Brak potwierdzenia” to brak dowodu, nawet jeśli w kolumnie odczytu widać
zapamiętane `off` lub niską moc. Nie oznacza ani potwierdzonego problemu, ani OK.
Problem ma pierwszeństwo w podsumowaniu, ale liczba nieocenionych kontroli nadal
pokazuje luki. Wykonanie ze wszystkimi kontrolami pominiętymi nie jest sukcesem.

**Anuluj kontrolę** zatrzymuje oczekiwanie lub próbkowanie. Restart przerywa
niedokończone wykonania. Żaden z tych stanów nie oznacza OK. Historia obejmuje
20 ostatnich wykonań wszystkich scenariuszy; nowy raport nie przepisuje starego.
Przy utracie połączenia lub braku odpowiedzi odśwież historię przed ponowieniem:
żądanie mogło zostać przyjęte. Ten sam scenariusz nie wykonuje się równolegle.

Raporty są dostępne w panelu. Osobna automatyzacja może reagować na zdarzenie
`safety_routine_completed`, np. wysłać powiadomienie. Dodanie scenariusza samo
nie tworzy tej automatyzacji. Kontrakt zdarzeń i ograniczenia opisuje
[architektura](../docs/features/Safety%20Routines%20-%20Architecture.md).
