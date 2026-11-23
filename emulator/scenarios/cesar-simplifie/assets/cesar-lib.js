/* Petite "librairie" du scenario : elle prouve que les ressources statiques
   sont bien servies et chargees par le navigateur, comme sur le vrai site. */
window.CesarLib = {
  version: '1.0.0',
  ready: true
};

document.documentElement.dataset.cesarLib = window.CesarLib.version;
