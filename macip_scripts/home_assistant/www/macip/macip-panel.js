import "./macip_filter.js";

const {ComparatorFilter, ipv4Value} = globalThis.MacipFilter;

class MacipPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._loaded = false;
    this._dirty = false;
    this._headers = [];
    this._devices = [];
    this._filters = [];
    this._selected = new Set();
    this._selectedOnly = false;
    this._visible = [];
    this._revision = null;
    this._busy = false;
    this._widths = {};
    this._sortColumn = -1;
    this._sortDirection = 1;
    this._collator = new Intl.Collator("fi", {numeric: true, sensitivity: "base"});
  }

  set hass(hass) {
    this._hass = hass;
    this._updateRefreshVisibility();
    if (this.isConnected && !this._loaded) {
      this._loaded = true;
      this._load();
    }
  }

  connectedCallback() {
    this._renderShell();
    if (this._hass && !this._loaded) {
      this._loaded = true;
      this._load();
    }
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { box-sizing: border-box; display: flex; height: calc(100vh - var(--header-height, 64px));
          height: calc(100dvh - var(--header-height, 64px)); padding: 20px;
          color: var(--primary-text-color); }
        main { display: flex; flex: 1; flex-direction: column; min-width: 0; min-height: 0; }
        main > * { flex-shrink: 0; }
        h1 { font-size: 1.5rem; }
        .toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; }
        button { border: 1px solid var(--divider-color); border-radius: 5px;
          background: var(--card-background-color); color: inherit; padding: .5rem .8rem;
          font: inherit; cursor: pointer; }
        button:disabled { cursor: not-allowed; opacity: .5; }
        #message { min-height: 1.5em; margin: .75rem 0; }
        #message.error { color: var(--error-color, #b42318); }
        .table-wrap { flex: 1 1 0; min-height: 6rem; overflow: auto; background: var(--card-background-color);
          border: 1px solid var(--divider-color); border-radius: 6px; }
        table { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 0;
          white-space: nowrap; font-size: .9rem; }
        th, td { padding: .3rem .5rem; border-bottom: 1px solid var(--divider-color);
          text-align: left; overflow: hidden; text-overflow: ellipsis; }
        th { position: relative; }
        thead { position: sticky; top: 0; z-index: 1; background: var(--secondary-background-color); }
        th button { border: 0; background: transparent; padding: 0; font-weight: 700; }
        th .sort-button { display: block; width: 100%; overflow: hidden; text-overflow: ellipsis;
          white-space: nowrap; text-align: left; }
        .filter { box-sizing: border-box; width: 100%; min-width: 0; padding: .25rem;
          border: 1px solid var(--divider-color); border-radius: 4px; font: inherit; }
        .filter.invalid { border-color: var(--error-color, #b42318); outline: 1px solid #b42318; }
        td input[type="text"] { box-sizing: border-box; width: 100%; min-width: 0;
          border: 1px solid transparent; border-radius: 3px; padding: .25rem;
          background: transparent; color: inherit; font: inherit; }
        td input[type="text"]:focus { border-color: var(--primary-color); outline: 1px solid var(--primary-color);
          background: var(--card-background-color); }
        .selection-cell { text-align: center; }
        .resize-handle { position: absolute; top: 0; right: 0; width: 8px; height: 100%;
          padding: 0; border: 0; background: transparent; cursor: col-resize; touch-action: none; }
        .resize-handle:hover, .resize-handle:focus-visible { background: var(--primary-color); opacity: .65; }
        .hint { color: var(--secondary-text-color); font-size: .9rem; }
        dialog { max-width: min(28rem, calc(100% - 3rem)); border: 1px solid var(--divider-color);
          border-radius: 6px; padding: 1.25rem; background: var(--card-background-color); color: inherit; }
        dialog::backdrop { background: rgba(0, 0, 0, .35); }
        dialog label { display: block; margin: .75rem 0; }
        dialog input { box-sizing: border-box; display: block; width: 100%; margin-top: .2rem;
          padding: .35rem; font: inherit; }
        #add-error { color: var(--error-color, #b42318); min-height: 1.5em; }
        @media (max-width: 600px), (max-height: 600px) {
          :host { padding: 8px; }
          main { overflow: auto; }
          .table-wrap { flex: 0 0 auto; overflow: visible; }
        }
        @media (max-height: 600px) {
          .hint { display: none; }
        }
      </style>
      <main>
        <h1>Verkon laiteluettelo</h1>
        <div class="toolbar">
          <button id="reload" type="button">Lataa uudelleen</button>
          <button id="update" type="button" disabled>Päivitä reitittimiltä</button>
          <button id="add" type="button" disabled>Lisää laite</button>
          <button id="delete" type="button" disabled>Poista valitut</button>
          <button id="save" type="button" disabled>Tallenna</button>
          <span id="count"></span>
        </div>
        <p id="message" role="status" aria-live="polite">Ladataan laiteluetteloa…</p>
        <div class="table-wrap">
          <table>
            <colgroup id="columns"></colgroup>
            <thead>
              <tr id="headers"></tr>
              <tr id="filters"></tr>
            </thead>
            <tbody id="rows"></tbody>
          </table>
        </div>
        <p class="hint">Otsikon ruutu valitsee näkyvät rivit ja suodatinrivin ruutu näyttää vain valitut.
          Poisto tallentuu vasta Tallenna-painikkeella. Suodattimet tukevat regexiä ja vertailuja, kuten =arvo, !teksti ja &gt;2&lt;4.
          Lajittele otsikosta ja muuta sarakkeen leveyttä sen oikeasta reunasta.</p>
      </main>
      <dialog id="add-dialog" aria-labelledby="add-title">
        <form id="add-form">
          <h2 id="add-title">Lisää laite</h2>
          <label>MAC-osoite <input id="new-mac" type="text" required autocomplete="off"></label>
          <label>IP-osoite <input id="new-ip" type="text" required autocomplete="off"></label>
          <label>Oma nimi <input id="new-name" type="text" autocomplete="off"></label>
          <p id="add-error" role="alert"></p>
          <button type="submit">Lisää</button>
          <button id="add-cancel" type="button">Peruuta</button>
        </form>
      </dialog>`;

    this.shadowRoot.getElementById("reload").addEventListener("click", () => this._load());
    this.shadowRoot.getElementById("update").addEventListener("click", () => this._updateInventory());
    this.shadowRoot.getElementById("add").addEventListener("click", () => this._addDevice());
    this.shadowRoot.getElementById("delete").addEventListener("click", () => this._deleteSelected());
    this.shadowRoot.getElementById("add-form").addEventListener("submit", event => this._submitDevice(event));
    this.shadowRoot.getElementById("add-cancel").addEventListener("click", () =>
      this.shadowRoot.getElementById("add-dialog").close());
    this.shadowRoot.getElementById("save").addEventListener("click", () => this._save());
    if (this._headers.length) this._renderTable();
  }

  _updateRefreshVisibility() {
    const button = this.shadowRoot.getElementById("update");
    if (button) button.hidden = false;
  }

  _showMessage(text, isError = false) {
    const message = this.shadowRoot.getElementById("message");
    message.textContent = text;
    message.classList.toggle("error", isError);
  }

  _setBusy(value) {
    this._busy = value;
    for (const id of ["reload", "update", "add", "save"]) {
      this.shadowRoot.getElementById(id).disabled = value || (id !== "reload" && !this._headers.length);
    }
    this.shadowRoot.getElementById("delete").disabled = value || this._selected.size === 0;
    const selectAll = this.shadowRoot.querySelector(".select-all");
    if (selectAll) selectAll.disabled = value || !this._visible.length;
    this.shadowRoot.querySelector("table").inert = value;
  }

  async _load(discardChanges = false) {
    if (this._dirty && !discardChanges && !window.confirm("Hylätäänkö tallentamattomat muutokset?")) {
      return;
    }
    this._setBusy(true);
    this._showMessage("Ladataan laiteluetteloa…");
    try {
      const result = await this._hass.callApi("GET", "macip");
      this._loadResult(result);
      this._showMessage("Laiteluettelo ladattu.");
    } catch (error) {
      this._showMessage(`Lataus epäonnistui: ${error.message}`, true);
    } finally {
      this._setBusy(false);
    }
  }

  _loadResult(result) {
      if (typeof result.revision !== "string") throw new Error("Tiedoston versio puuttuu.");
      const lines = result.content.replace(/^\uFEFF/, "").split(/\r?\n/).filter(line => line.trim());
      if (!lines.length || !lines[0].includes("|")) {
        throw new Error("Tiedostosta ei löytynyt otsikkoriviä tai erotinta '|'.");
      }
      const headers = lines[0].split("|").map(value => value.trim());
      if (headers[0]?.toLowerCase() !== "mac" || !headers.includes("IP") || !headers.includes("Oma nimi")) {
        throw new Error("Tiedoston otsikoissa pitää olla MAC-, IP- ja Oma nimi -sarakkeet.");
      }
      const devices = lines.slice(1).map((line, index) => {
        const values = line.split("|").map(value => value.trim());
        if (values.length !== headers.length) {
          throw new Error(`Rivillä ${index + 2} on virheellinen määrä sarakkeita.`);
        }
        return values;
      });
      for (const column of ["Yhteys", "Signaali", "Tukiasema"]) {
        if (!headers.includes(column)) {
          headers.push(column);
          devices.forEach(values => values.push(""));
        }
      }

      this._headers = headers;
      this._devices = devices;
      this._revision = result.revision;
      this._selected.clear();
      this._selectedOnly = false;
      this._filters = headers.map(() => "");
      this._sortColumn = headers.findIndex(header => header.toLowerCase() === "ip");
      this._sortDirection = 1;
      this._dirty = false;
      this.shadowRoot.getElementById("save").textContent = "Tallenna";
      try {
        const widths = JSON.parse(localStorage.getItem("macipColumnWidths") || "{}");
        this._widths = widths && typeof widths === "object" && !Array.isArray(widths) ? widths : {};
      } catch (error) {
        this._widths = {};
        this._showMessage(`Sarakkeiden leveyksiä ei voitu lukea: ${error.message}`, true);
      }
      this._renderTable();
  }

  async _updateInventory() {
    if (this._dirty) {
      this._showMessage("Tallenna tai hylkää muutokset ennen reititinpäivitystä.", true);
      return;
    }

    this._setBusy(true);
    this._showMessage("Haetaan laitteita reitittimiltä…");
    try {
      const result = await this._hass.callApi("POST", "macip/update", {revision: this._revision});
      if (!Array.isArray(result.summaries) || !Array.isArray(result.failures)
          || !Array.isArray(result.missing_summaries)) {
        throw new Error("Palvelin ei palauttanut reititinpäivityksen yhteenvetoa.");
      }
      this._loadResult(result);
      this._showUpdateSummaries(result.summaries, result.failures);
      const warnings = [];
      if (result.failures.length) warnings.push(`Epäonnistui: ${result.failures.map(x => x.command).join(", ")}.`);
      if (result.missing_summaries.length) warnings.push(`Yhteenveto puuttuu: ${result.missing_summaries.join(", ")}.`);
      this._showMessage(warnings.length ? `Päivitys valmis. ${warnings.join(" ")}` : "Reititinpäivitys valmis.",
        warnings.length > 0);
    } catch (error) {
      this._showMessage(`Reititinpäivitys epäonnistui: ${error?.message || String(error)}`, true);
    } finally {
      this._setBusy(false);
    }
  }

  _showUpdateSummaries(summaries, failures = []) {
    const sections = [];
    for (const summary of summaries) {
      const lines = [];
      for (const device of summary.new_devices) {
        const label = device.name && !["--", "0"].includes(device.name)
          ? `${device.name} (${device.mac})` : device.mac;
        lines.push(`Uusi: ${label}, IP ${device.ip || "--"}`);
      }
      for (const device of summary.ip_changes) {
        const label = device.name && !["--", "0"].includes(device.name)
          ? `${device.name} (${device.mac})` : device.mac;
        lines.push(`IP: ${label}: ${device.old_ip || "--"} → ${device.new_ip || "--"}`);
      }
      if (lines.length) sections.push(`${summary.router}\n${lines.join("\n")}`);
    }
    const messages = [];
    if (sections.length) messages.push(`Reititinpäivityksen muutokset:\n\n${sections.join("\n\n")}`);
    if (failures.length) messages.push(`Epäonnistuneet päivitykset:\n\n${failures.map(
      failure => `${failure.command}: ${failure.error}`).join("\n\n")}`);
    if (messages.length) window.alert(messages.join("\n\n"));
  }

  _addDevice() {
    this.shadowRoot.getElementById("add-form").reset();
    this.shadowRoot.getElementById("add-error").textContent = "";
    this.shadowRoot.getElementById("add-dialog").showModal();
    this.shadowRoot.getElementById("new-mac").focus();
  }

  _submitDevice(event) {
    event.preventDefault();
    const macInput = this.shadowRoot.getElementById("new-mac");
    const ipInput = this.shadowRoot.getElementById("new-ip");
    const nameInput = this.shadowRoot.getElementById("new-name");
    const error = this.shadowRoot.getElementById("add-error");
    const mac = macInput.value.trim().toLowerCase();
    if (!/^(?:[0-9a-f]{12}|[0-9a-f]{2}(?::[0-9a-f]{2}){5}|[0-9a-f]{2}(?:-[0-9a-f]{2}){5})$/.test(mac)) {
      error.textContent = "Virheellinen MAC-osoite. Anna esimerkiksi 00:11:22:33:44:55.";
      macInput.focus();
      return;
    }
    const normalizedMac = mac.replace(/[:-]/g, "");
    if (this._devices.some(row => row[0].toLowerCase().replace(/[:-]/g, "") === normalizedMac)) {
      error.textContent = "Tämä MAC-osoite on jo luettelossa.";
      macInput.focus();
      return;
    }

    const ip = ipInput.value.trim();
    const validIpv4 = ipv4Value(ip) !== null;
    let validIpv6 = false;
    if (ip.includes(":") && /^[0-9a-f:.]+$/i.test(ip)) {
      try {
        validIpv6 = new URL(`http://[${ip}]/`).hostname.startsWith("[");
      } catch {
        validIpv6 = false;
      }
    }
    if (!validIpv4 && !validIpv6) {
      error.textContent = "Virheellinen IP-osoite.";
      ipInput.focus();
      return;
    }
    const name = nameInput.value.trim();
    if (/[|\r\n]/.test(name)) {
      error.textContent = "Nimi ei voi sisältää erotinta '|' tai rivinvaihtoa.";
      nameInput.focus();
      return;
    }

    const row = this._headers.map(() => "");
    row[0] = normalizedMac.match(/.{2}/g).join(":");
    row[this._headers.indexOf("IP")] = ip;
    row[this._headers.indexOf("Oma nimi")] = name;
    this._devices.push(row);
    this._dirty = true;
    this.shadowRoot.getElementById("save").textContent = "Tallenna *";
    this._renderRows();
    this.shadowRoot.getElementById("add-dialog").close();
    this._showMessage("Laite lisätty. Jos riviä ei näy, tarkista suodattimet. Muista tallentaa.");
  }

  _deleteSelected() {
    const count = this._selected.size;
    if (!count) return;
    const hidden = count - this._visible.filter(({values}) => this._selected.has(values)).length;
    const note = hidden ? ` Näistä ${hidden} ei näy nykyisillä suodattimilla.` : "";
    if (!window.confirm(`Poistetaanko ${count} valittua laitetta?${note} Muutos tallentuu vasta Tallenna-painikkeella.`)) return;
    this._devices = this._devices.filter(values => !this._selected.has(values));
    this._selected.clear();
    this._dirty = true;
    this.shadowRoot.getElementById("save").textContent = "Tallenna *";
    this._renderRows();
    this._showMessage(`${count} laitetta poistettu. Muista tallentaa.`);
  }

  _renderTable() {
    const headersRow = this.shadowRoot.getElementById("headers");
    const filtersRow = this.shadowRoot.getElementById("filters");
    const columns = this.shadowRoot.getElementById("columns");
    if (!headersRow || !filtersRow) return;
    headersRow.replaceChildren();
    filtersRow.replaceChildren();
    columns.replaceChildren();

    const selectionColumn = document.createElement("col");
    selectionColumn.style.width = "44px";
    columns.append(selectionColumn);
    const selectionHeading = document.createElement("th");
    selectionHeading.className = "selection-cell";
    const selectAll = document.createElement("input");
    selectAll.type = "checkbox";
    selectAll.className = "select-all";
    selectAll.setAttribute("aria-label", "Valitse tai poista valinta näkyviltä riveiltä");
    selectAll.addEventListener("change", () => {
      for (const {values} of this._visible) {
        if (selectAll.checked) this._selected.add(values);
        else this._selected.delete(values);
      }
      this._renderRows();
    });
    selectionHeading.append(selectAll);
    headersRow.append(selectionHeading);
    const selectionFilterCell = document.createElement("th");
    selectionFilterCell.className = "selection-cell";
    const selectionFilter = document.createElement("input");
    selectionFilter.type = "checkbox";
    selectionFilter.checked = this._selectedOnly;
    selectionFilter.setAttribute("aria-label", "Näytä vain valitut rivit");
    selectionFilter.addEventListener("change", () => {
      this._selectedOnly = selectionFilter.checked;
      this._renderRows();
    });
    selectionFilterCell.append(selectionFilter);
    filtersRow.append(selectionFilterCell);

    this._headers.forEach((header, index) => {
      const column = document.createElement("col");
      column.style.width = `${this._columnWidth(header)}px`;
      columns.append(column);
      const heading = document.createElement("th");
      heading.scope = "col";
      const sortButton = document.createElement("button");
      sortButton.type = "button";
      sortButton.className = "sort-button";
      sortButton.textContent = header;
      sortButton.addEventListener("click", () => {
        if (this._sortColumn === index) this._sortDirection *= -1;
        else {
          this._sortColumn = index;
          this._sortDirection = 1;
        }
        this._renderRows();
      });
      heading.append(sortButton);
      const resize = document.createElement("button");
      resize.type = "button";
      resize.className = "resize-handle";
      resize.setAttribute("aria-label", `Muuta sarakkeen ${header} leveyttä`);
      resize.addEventListener("pointerdown", event => {
        event.preventDefault();
        const startX = event.clientX;
        const startWidth = column.getBoundingClientRect().width;
        resize.setPointerCapture(event.pointerId);
        resize.onpointermove = move => this._resizeColumn(index, startWidth + move.clientX - startX);
        resize.onpointerup = resize.onpointercancel = end => {
          this._resizeColumn(index, startWidth + end.clientX - startX);
          resize.onpointermove = resize.onpointerup = resize.onpointercancel = null;
          this._saveWidths();
        };
      });
      resize.addEventListener("keydown", event => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        this._resizeColumn(index, this._columnWidth(header) + (event.key === "ArrowRight" ? 10 : -10));
        this._saveWidths();
      });
      heading.append(resize);
      headersRow.append(heading);

      const filterCell = document.createElement("th");
      const filter = document.createElement("input");
      filter.type = "search";
      filter.className = "filter";
      filter.setAttribute("aria-label", `Suodatin: ${header}`);
      filter.addEventListener("input", () => {
        this._filters[index] = filter.value;
        this._renderRows();
      });
      filterCell.append(filter);
      filtersRow.append(filterCell);
    });
    this._updateTableWidth();
    this._renderRows();
  }

  _columnWidth(header) {
    const saved = this._widths[header];
    if (Number.isFinite(saved) && saved >= 48 && saved <= 2000) return Math.round(saved);
    const defaults = {"MAC": 135, "IP": 120, "Nimi": 120, "Reitittimen nimi": 150,
      "Oma nimi": 190, "Tila": 72, "Viimeksi nähty": 155, "Yhteys": 95, "Signaali": 68, "Tukiasema": 135};
    return defaults[header] || 140;
  }

  _updateTableWidth() {
    const width = this._headers.reduce((sum, header) => sum + this._columnWidth(header), 44);
    this.shadowRoot.querySelector("table").style.width = `${width}px`;
  }

  _resizeColumn(index, width) {
    const bounded = Math.round(Math.max(48, Math.min(2000, width)));
    this._widths[this._headers[index]] = bounded;
    this.shadowRoot.getElementById("columns").children[index + 1].style.width = `${bounded}px`;
    this._updateTableWidth();
  }

  _saveWidths() {
    try {
      localStorage.setItem("macipColumnWidths", JSON.stringify(this._widths));
    } catch (error) {
      this._showMessage(`Sarakkeiden leveyksien tallennus epäonnistui: ${error.message}`, true);
    }
  }

  _renderRows() {
    const filtersRow = this.shadowRoot.getElementById("filters");
    const tableBody = this.shadowRoot.getElementById("rows");
    if (!filtersRow || !tableBody) return;
    const expressions = [];
    let invalidFilter = false;

    this._headers.forEach((_, index) => {
      const input = filtersRow.children[index + 1]?.querySelector("input");
      try {
        expressions[index] = this._filters[index]
          ? new ComparatorFilter(this._filters[index], this._headers[index] === "IP")
          : null;
        input?.classList.remove("invalid");
        input?.removeAttribute("aria-invalid");
      } catch {
        expressions[index] = null;
        invalidFilter = true;
        input?.classList.add("invalid");
        input?.setAttribute("aria-invalid", "true");
      }
    });

    const visible = this._devices
      .map((values, originalIndex) => ({values, originalIndex}))
      .filter(({values}) => (!this._selectedOnly || this._selected.has(values)) && expressions.every((expression, index) =>
        !expression || expression.test(values[index] || "")
      ));

    if (this._sortColumn >= 0) {
      visible.sort((left, right) =>
        this._collator.compare(
          left.values[this._sortColumn] || "",
          right.values[this._sortColumn] || ""
        ) * this._sortDirection
      );
    }

    this._visible = visible;
    tableBody.replaceChildren();
    const ownNameIndex = this._headers.indexOf("Oma nimi");
    visible.forEach(({values, originalIndex}) => {
      const row = document.createElement("tr");
      const selectionCell = document.createElement("td");
      selectionCell.className = "selection-cell";
      const selection = document.createElement("input");
      selection.type = "checkbox";
      selection.checked = this._selected.has(values);
      selection.setAttribute("aria-label", `Valitse laite ${values[0]}`);
      selection.addEventListener("change", () => {
        if (selection.checked) this._selected.add(values);
        else this._selected.delete(values);
        this._renderRows();
      });
      selectionCell.append(selection);
      row.append(selectionCell);
      values.forEach((value, columnIndex) => {
        const cell = document.createElement("td");
        if (this._headers[columnIndex] === "Reitittimen nimi") {
          cell.classList.add("router-name");
          cell.title = value;
        }
        if (columnIndex === ownNameIndex) {
          const input = document.createElement("input");
          input.type = "text";
          input.value = value;
          input.setAttribute("aria-label", `${values[0]}: oma nimi`);
          input.addEventListener("input", () => {
            this._devices[originalIndex][ownNameIndex] = input.value;
            this._dirty = true;
            this.shadowRoot.getElementById("save").textContent = "Tallenna *";
            this._showMessage("Muutoksia ei ole vielä tallennettu.");
          });
          cell.append(input);
        } else {
          cell.textContent = value;
        }
        row.append(cell);
      });
      tableBody.append(row);
    });

    const selectedVisible = visible.filter(({values}) => this._selected.has(values)).length;
    const selectAll = this.shadowRoot.querySelector(".select-all");
    selectAll.checked = visible.length > 0 && selectedVisible === visible.length;
    selectAll.indeterminate = selectedVisible > 0 && selectedVisible < visible.length;
    selectAll.disabled = this._busy || !visible.length;
    this.shadowRoot.getElementById("delete").disabled = this._busy || !this._selected.size;
    this.shadowRoot.getElementById("count").textContent =
      `${visible.length} / ${this._devices.length} laitetta, ${this._selected.size} valittu`;
    if (invalidFilter) this._showMessage("Virheellinen suodatin tai regex (punainen kenttä).", true);
    else if (this._devices.length) this._showMessage(this._dirty ? "Muutoksia ei ole vielä tallennettu." : "Luettelo ladattu.");
  }

  _formatInventory() {
    const rows = [this._headers, ...this._devices];
    if (this._devices.some(row => row.some(value => /[|\r\n]/.test(value)))) {
      throw new Error("Sarake ei voi sisältää erotinta '|' tai rivinvaihtoa.");
    }
    const widths = this._headers.map((_, column) =>
      Math.max(...rows.map(row => (row[column] || "").length))
    );
    return rows.map(row =>
      row.map((value, column) => (value || "").padEnd(widths[column])).join(" | ")
    ).join("\n") + "\n";
  }

  async _save() {
    this._setBusy(true);
    try {
      const result = await this._hass.callApi("POST", "macip", {
        content: this._formatInventory(), revision: this._revision
      });
      if (typeof result.revision !== "string") throw new Error("Tallennettu versio puuttuu.");
      this._revision = result.revision;
      this._dirty = false;
      this.shadowRoot.getElementById("save").textContent = "Tallenna";
      this._showMessage("Muutokset tallennettu Home Assistantiin.");
    } catch (error) {
      this._showMessage(`Tallennus epäonnistui: ${error.message}`, true);
    } finally {
      this._setBusy(false);
    }
  }
}

customElements.define("macip-panel", MacipPanel);
