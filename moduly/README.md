# Moduly vazeb

Modul = textový soubor příkazů, které se dají pustit do libovolné paměti
(`!načti-vazby soubor.txt`); z paměti se naučené vazby vypíší zpět
(`!ulož-vazby soubor.txt`). Modul nenese fakta, jen vazby: `!role`,
`!synonymum`, `!srovnání`, `!uč složený | inverze | překryv | porovnání`,
`!pravidlo`, `!výjimka`. Řádky s `#` jsou komentář; věta bez `!` se
zapíše jako v dialogu (definice v přirozeném jazyce, např. „Tchán je otec
manžela nebo manželky.“).

| soubor | co dává |
|---|---|
| `cas_a_veliciny.txt` | starší/mladší z data narození, potkat_se ⇐ překryv žít(kdy), vejít ⇐ délka <= |

Vrstvení: fakta z textu (vrstva 1) + vazby z modulu (vrstva 2) → odvozené
verdikty nesou řetěz až k větám. Vazba, jejíž vstupy v paměti nejsou, jen
čeká — nic netvrdí.
