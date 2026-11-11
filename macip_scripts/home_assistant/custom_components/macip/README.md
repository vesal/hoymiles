# MAC/IP-editori Home Assistantissa

## Uusi asennus

Alla lähdepolut ovat tämän projektin juuresta ja kohdepolut Home Assistantin
`/config`-hakemistosta. Luo kohdehakemistot tarvittaessa.

- Kopioi `macip_scripts/home_assistant/custom_components/macip/
  → `/config/custom_components/macip/
     - `__init__.py`
     - `http.py`
     - `manifest.json`
- Kopioi `macip_scripts/home_assistant/www/macip-panel.js`
  → `/config/www/macip/macip-panel.js`
- Kopioi `macip_scripts/macip_filter.js`
  → `/config/www/macip/macip_filter.js`
- Kopioi `macip_scripts/`
  → `/config/macip_scripts/`
     - `asus_mac.py`
     - `huawei_lan_inventory.py`
     - `macip_common.py`
	 - `macip_server_config.json`
	    - ks muokkausohje alempana
- Kopioi omat reitittimien asetustiedostot, esimerkiksi `secret2.txt` ja
  `secret3.txt` → `/config/macip_scripts/`
     - ks: `macip_scripts/macip_server_ohje.txt`
	 - osoite pitää olla: `macip=/config/macip_scripts/macip.txt`

Jos `macip.txt` puuttuu, Home Assistant luo sen otsikoineen, kun editori
avataan ensimmäisen kerran. Olemassa olevaa tiedostoa ei korvata.

### Asetukset

1. Muokkaa `/config/macip_scripts/macip_server_config.json` niin, että
   `update_commands` sisältää omat skriptisi ja niiden asetustiedostot halutussa
   suoritusjärjestyksessä. Polut ovat suhteessa `macip_scripts`-hakemistoon, esimerkiksi:

   ```json
   {
     "update_commands": [
       ["asus_mac.py", "secret3.txt"],
       ["asus_mac.py", "secret2.txt"],
       ["huawei_lan_inventory.py", "secret1.txt"]
     ]
   }
   ```

2. Aseta jokaisessa reitittimen asetustiedostossa sama tiedostopolku:

   ```text
   macip=/config/macip_scripts/macip.txt
   ```

   Täytä myös kunkin reitittimen omat yhteys- ja kirjautumistiedot.
   Huawei-asetuksille on pohja `macip_scripts/huawei_config_example.txt`.
   ASUS-nimien synkronoinnin ja muut asetukset selittää
   `macip_scripts/macip_server_ohje.txt`.

3. Jos kopioit olemassa olevan `macip.txt`-tiedoston, varmista että se on
   UTF-8-koodattu ja sen otsikkorivi on jompikumpi:

   ```text
   MAC | IP | Nimi | Oma nimi | Tila | Viimeksi nähty
   MAC | IP | Nimi | Oma nimi | Tila | Viimeksi nähty | Yhteys | Signaali | Tukiasema
   ```

4. Lisää Home Assistantin `/config/configuration.yaml`-tiedostoon seuraavat
   asetukset. Jos `panel_custom` on jo määritelty, lisää vain uusi listan kohta
   olemassa olevan `panel_custom`-avaimen alle.

   ```yaml
   macip:

   panel_custom:
     - name: macip-panel
       sidebar_title: MAC/IP
       sidebar_icon: mdi:lan
       url_path: macip
       module_url: /local/macip-panel.js
   ```

5. Käynnistä Home Assistant uudelleen ja avaa sivupalkista **MAC/IP**.

   Reititinskriptit tarvitsevat Pythonin `requests`-paketin. Se kuuluu
   Home Assistant Coren riippuvuuksiin, joten sitä ei tavallisesti tarvitse
   asentaa erikseen.

   Jos päivityksessä kuitenkin näkyy virhe `No module named 'requests'`,
   paketti pitää asentaa samaan Python-ympäristöön, jossa Home Assistant
   toimii. Jos käytät omaa Python-virtuaaliympäristöä, aktivoi se ja suorita:

   ```bash
   python3 -m pip install requests
   ```

   Home Assistant OS:n terminaalilisäosa käyttää eri ympäristöä kuin
   Home Assistant Core, joten siellä annettu asennuskomento ei välttämättä
   asenna pakettia Coren käyttöön.

Paneeli lukee ja tallentaa listan kirjautumista vaativan rajapinnan kautta.
Reititinpäivitykset suoritetaan asetetussa järjestyksessä, myös yksittäisen
komennon epäonnistuessa. Editori näyttää virheet ja estää vanhentuneen
näkymän tallentamisen.

## Siirtyminen vanhasta editor-hakemistosta

1. Pysäytä Home Assistant ja ota varmuuskopio tiedostoista.
2. Siirrä `/config/macip_scripts/editor/`-hakemiston sisältö hakemistoon
   `/config/macip_scripts/`, myös `macip.txt` ja reitittimien asetustiedostot.
   Älä korvaa mahdollisia ennestään samannimisiä tiedostoja tarkistamatta niitä.
3. Muuta kunkin reitittimen asetustiedoston `macip`-poluksi
   `/config/macip_scripts/macip.txt`. Tarkista myös mahdolliset muut vanhaan
   hakemistoon viittaavat polut ja komennot.
4. Kopioi uusi integraation `http.py` tiedostoon
   `/config/custom_components/macip/http.py` ja käynnistä Home Assistant.
   Tarkista, että editorissa näkyy aiempi laitelista ja reititinpäivitys toimii.
   Tyhjän `editor`-hakemiston voi tämän jälkeen poistaa.
