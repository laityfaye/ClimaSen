/*
 * Harnais de test du JavaScript du widget Jarvis, sans navigateur.
 *
 * Simule le strict necessaire du DOM et surtout la situation qui compte :
 * un script qui tourne DANS une iframe, dont les dimensions propres (76 px de
 * haut repliee) n ont rien a voir avec celles de la page hote (590 px).
 *
 * C est precisement ce que le widget confondait : il comparait la position de
 * la bulle dans la page hote a la hauteur de sa propre iframe, en concluait
 * que la bulle etait hors ecran, et effacait son style. La bulle devenait
 * invisible.
 *
 * Usage : node tests/widget_harness.js <fichier.js>
 * Sortie : une ligne "OK <verification>" par controle, ou "ECHEC ..." + code 1.
 */
const fs = require("fs");

const HOTE = { w: 1361, h: 590 };     // fenetre du navigateur
const MARGE = 18;

let echecs = [];
function verifier(nom, condition, detail) {
  if (condition) { console.log("OK    " + nom); }
  else { console.log("ECHEC " + nom + (detail ? " -> " + detail : "")); echecs.push(nom); }
}

// --- Stubs DOM minimaux -----------------------------------------------------
function style() {
  const s = {
    _props: {},
    setProperty(k, v) { s._props[k] = v; },
    removeProperty(k) { delete s._props[k]; },
    get cssText() { return JSON.stringify(s._props); },
    set cssText(v) { if (v === "") s._props = {}; },
  };
  return new Proxy(s, {
    set(cible, cle, valeur) {
      if (cle === "cssText" && valeur === "") { cible._props = {}; return true; }
      cible[cle] = valeur; return true;
    },
    get(cible, cle) { return cible[cle]; },
  });
}

function element(id) {
  return {
    id,
    style: style(),
    value: "",
    disabled: false,
    scrollHeight: 20, scrollTop: 0,
    textContent: "", innerHTML: "",
    classList: { add() {}, remove() {}, contains() { return false; } },
    addEventListener() {}, appendChild() {}, removeChild() {},
    querySelectorAll() { return []; },
    focus() {},
    parentNode: null,
  };
}

// L iframe telle que la voit le script : style pilotable, et une position
// dans la PAGE HOTE (en bas a droite), pas dans l iframe.
const frame = {
  style: style(),
  getBoundingClientRect() {
    const h = parseInt((frame.style._props.height || "76px"), 10);
    const w = parseInt((frame.style._props.width || "360px"), 10);
    return {
      width: w, height: h,
      left: HOTE.w - MARGE - w, right: HOTE.w - MARGE,
      top: HOTE.h - MARGE - h, bottom: HOTE.h - MARGE,
    };
  },
};

// Second argument : "ouvert" pour simuler une restauration apres une
// reexecution Streamlit, panneau precedemment ouvert.
const OUVERT = process.argv[3] === "ouvert";
const stockage = OUVERT ? { jarvis_open: "1" } : {};
const elements = {};
["panel", "log", "intro", "input", "send", "fab", "banner", "dot", "status", "close",
 "typing"].forEach((id) => { elements[id] = element(id); });

global.sessionStorage = {
  getItem: (k) => (k in stockage ? stockage[k] : null),
  setItem: (k, v) => { stockage[k] = String(v); },
  removeItem: (k) => { delete stockage[k]; },
};

global.document = {
  documentElement: { setAttribute() {} },
  body: { classList: { add() {}, remove() {} }, appendChild() {} },
  getElementById: (id) => elements[id] || element(id),
  createElement: () => element("cree"),
  querySelectorAll: () => [],
  addEventListener() {},
};

// La fenetre HOTE : c est elle qui fait 590 px de haut.
const parent = {
  innerWidth: HOTE.w, innerHeight: HOTE.h,
  addEventListener() {}, postMessage() {},
  document: { querySelectorAll: () => [] },
};

// La fenetre de l IFRAME : 76 px de haut quand la bulle est repliee.
// Toute la subtilite du test est la.
global.window = {
  innerWidth: 360, innerHeight: 76,
  parent, frameElement: frame,
  addEventListener() {}, postMessage() {},
  location: { search: "" },
};
global.TextDecoder = class { decode() { return ""; } };
global.fetch = () => Promise.reject(new Error("reseau coupe dans le harnais"));

// --- Execution du script du widget ------------------------------------------
const code = fs.readFileSync(process.argv[2], "utf8");
try {
  new Function("window", "document", "sessionStorage", "fetch", "TextDecoder", code)(
    global.window, global.document, global.sessionStorage, global.fetch, global.TextDecoder);
} catch (e) {
  console.log("ECHEC execution du script -> " + e.message);
  process.exit(1);
}

// --- Verifications immediates ------------------------------------------------
const p = frame.style._props;
verifier("la bulle est epinglee en position fixe", p.position === "fixed", JSON.stringify(p));
verifier("la bulle a une largeur", parseInt(p.width, 10) >= 300, p.width);
verifier("la bulle a une hauteur repliee visible", parseInt(p.height, 10) >= 50, p.height);
verifier("la bulle est au-dessus du contenu", parseInt(p["z-index"], 10) > 1000, p["z-index"]);

// --- Le controle de visibilite ne doit pas effacer la bulle -------------------
// Il s execute 300 ms apres le montage.
setTimeout(() => {
  const apres = frame.style._props;
  verifier("le filet de securite n a pas efface la bulle",
           apres.position === "fixed" && parseInt(apres.height, 10) >= 50,
           "style apres controle : " + JSON.stringify(apres));

  if (OUVERT) {
    // Le panneau etait ouvert avant la reexecution Streamlit : il doit etre
    // rouvert, et sa hauteur doit se deduire de la fenetre HOTE (590 px), pas
    // de celle de l iframe. Attendu : max(360, min(560, 590-150)) = 440.
    // Un script qui lirait window.innerHeight obtiendrait 360, le plancher.
    const hauteur = parseInt(apres.height, 10);
    verifier("le panneau est rouvert apres une reexecution Streamlit",
             hauteur > 100, "hauteur " + apres.height);
    verifier("sa hauteur suit la fenetre hote et non l iframe",
             hauteur === 440, "attendu 440 px, obtenu " + apres.height);
  }

  if (echecs.length) {
    console.log("\n" + echecs.length + " verification(s) en echec");
    process.exit(1);
  }
  console.log("\nToutes les verifications passent");
  process.exit(0);
}, 400);
