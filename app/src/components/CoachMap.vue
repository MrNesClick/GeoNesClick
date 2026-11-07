<script setup lang="ts">
// Onglet Carte (niveau 3 et plus) : pays probables colorés selon StreetCLIP, pays écartés grisés par une
// preuve forte, et les ZONES où la vue se trouve probablement (positions PLONK regroupées par le moteur).
// Au niveau 4, une preuve forte recadre sur son pays. Les LIEUX LUS sur tes marques sont placés (GeoNames), et
// les distances d'un panneau directionnel donnent une position estimée à quelques km : elle passe avant les zones.
// Fond OpenStreetMap en ligne, assombri par un filtre CSS ; sans réseau, pays, zones et lieux restent dessinés.
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { Analysis, Lock, Zone } from "../engine";
import { certainProof, circled, countryName, countryOutlines, engine, flag, fr, headCountry, openAttribution, visibleZones } from "../engine";

const props = defineProps<{ analysis: Analysis; level: number }>();

const el = ref<HTMLDivElement | null>(null);
const outlinesMissing = ref(false);
let map: L.Map | null = null;
let outlines: L.GeoJSON | null = null;
let zoneLayer: L.LayerGroup | null = null;
let placeLayer: L.LayerGroup | null = null;
let resize: ResizeObserver | null = null;

const css = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
const COLORS = {
  foret: css("--color-foret", "#7db38a"),
  lac: css("--color-lac", "#7fb6d6"),
  courbe: css("--color-courbe", "#8a9aa6"),
  courbeFonce: css("--color-courbe-fonce", "#2b3d4f"),
  encre: css("--color-encre", "#15202b"),
  marque: css("--color-marque", "#f2c14e"),
};
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const certain = computed(() => certainProof(props.analysis));
/** Pays en tête : prouvé, ou lu par l'IA (très probable, les autres restent colorés). */
const head = computed(() => headCountry(props.analysis));
/** Zones PLONK (allure de la vue) : masquées dès que tes marques situent la vue, bien plus précisément. */
const zones = computed(() => (props.analysis.verdict?.location ? [] : visibleZones(props.analysis)));
const zonesHidden = computed(() => !!props.analysis.verdict?.location && visibleZones(props.analysis).length > 0);
const LABELS_ZOOM = 9; // en dessous, les noms des lieux lus se chevauchent : seuls les points restent
/** Position estimée d'après tes marques (lieux lus, distances d'un panneau). */
const location = computed(() => props.analysis.verdict?.location ?? null);
const coords = (lat: number, lon: number) =>
  `${lat.toFixed(4).replace(".", ",")}° ${lat >= 0 ? "N" : "S"}, ${lon.toFixed(4).replace(".", ",")}° ${lon >= 0 ? "E" : "O"}`;
const distances = computed(() => location.value?.places.filter((p) => p.km) ?? []);
/** Lieu lu le plus proche (plus petite distance du panneau). */
const nearestRead = computed(() => [...distances.value].sort((a, b) => a.km! - b.km!)[0] ?? null);
// Ce qui est sûr (tes choix, ou ceux du coach au niveau qui les dévoile) : la carte se cadre dessus.
const shownLock = (l?: Lock) => (l && (l.by === "user" || props.level >= (l.level === "country" ? 3 : 4)) ? l : null);
const lockCountry = computed(() => shownLock(props.analysis.locks?.held.country));
const lockRegion = computed(() => shownLock(props.analysis.locks?.held.region));
const lockCity = computed(() => shownLock(props.analysis.locks?.held.city));
const regionBounds = computed(() => (lockRegion.value ? props.analysis.locks?.region_bounds ?? null : null));
const outside = computed(() => props.analysis.verdict?.outside ?? []);
const probability = (code: string) => props.analysis.scores?.find((s) => s.code === code)?.probability ?? 0;
const pct = (p: number) => `${Math.round(p * 100)} %`;
/** Taille lisible : arrondie à 10 km, à 50 km au-delà de 200 km. */
const roundKm = (km: number) => {
  const step = km > 200 ? 50 : 10;
  return Math.max(10, Math.round(km / step) * step);
};

function styleFor(code: string): L.PathOptions {
  const proven = certain.value?.country ?? lockCountry.value?.country; // prouvé, ou dit sûr
  if (!proven && code === head.value?.code) {
    return { color: COLORS.lac, weight: 1.6, dashArray: "6 4", fillColor: COLORS.lac, fillOpacity: 0.12 };
  }
  if (proven) {
    if (code === proven) return { color: COLORS.lac, weight: 1.6, fillColor: COLORS.lac, fillOpacity: 0.12 };
    if (probability(code) > 0) {
      return { color: COLORS.courbe, weight: 0.8, dashArray: "3 3", fillColor: COLORS.encre, fillOpacity: 0.45 };
    }
  } else if (probability(code) > 0) {
    const p = probability(code);
    return { color: COLORS.foret, weight: 1, fillColor: COLORS.foret, fillOpacity: 0.06 + 0.3 * p };
  }
  return { color: COLORS.courbeFonce, weight: 0.5, fillOpacity: 0 };
}

const codeOf = (f?: GeoJSON.Feature) => String(f?.properties?.code ?? "");

function countryBounds(code: string): L.LatLngBounds | null {
  let bounds: L.LatLngBounds | null = null;
  outlines?.eachLayer((layer) => {
    const poly = layer as L.Polygon;
    if (codeOf(poly.feature) !== code) return;
    bounds = bounds ? bounds.extend(poly.getBounds()) : poly.getBounds();
  });
  return bounds;
}

const union = (all: (L.LatLngBounds | null)[]) =>
  all.reduce<L.LatLngBounds | null>((acc, b) => (b ? (acc ? acc.extend(b) : L.latLngBounds(b.getSouthWest(), b.getNorthEast())) : acc), null);

function locationBounds(): L.LatLngBounds | null {
  const loc = location.value;
  if (!loc) return null;
  if (loc.kind === "places") {
    const b = L.latLngBounds(loc.places.map((p) => [p.lat, p.lon] as L.LatLngTuple));
    return b.pad(0.4);
  }
  return L.latLng(loc.lat, loc.lon).toBounds(loc.radius_km * 2000 * 1.6); // le cercle et un peu d'alentour
}

function frame(): L.LatLngBounds | null {
  const city = lockCity.value;
  if (city?.lat != null && city.lon != null) return L.latLng(city.lat, city.lon).toBounds(5000); // la ville choisie
  const here = locationBounds(); // tes marques situent la vue : plus précis que tout le reste
  if (here) return here;
  const rb = regionBounds.value; // la région choisie, d'après l'étendue de ses lieux
  if (rb) return L.latLngBounds([rb[0], rb[1]], [rb[2], rb[3]]).pad(0.05);
  if (lockCountry.value) return countryBounds(lockCountry.value.country);
  const top = head.value?.code;
  if (props.level >= 4 && top) return countryBounds(top); // la réponse : on resserre sur le pays en tête
  if (zones.value.length) return union(zones.value.map((z) => L.latLngBounds(z.polygon)));
  // Sans zone : les pays probables (au-dessus de 5 %, trois au plus).
  const codes = (props.analysis.scores ?? []).filter((s) => s.probability >= 0.05).slice(0, 3).map((s) => s.code);
  return union(codes.map(countryBounds));
}

function drawZone(zone: Zone, rank: number) {
  L.polygon(zone.polygon, {
    color: COLORS.lac,
    weight: rank === 0 ? 2.5 : 1.5,
    dashArray: rank === 0 ? undefined : "6 4",
    fillColor: COLORS.lac,
    fillOpacity: 0.1 + 0.25 * zone.part,
    interactive: false,
  })
    .bindTooltip(`${rank + 1} · ${pct(zone.part)}`, { permanent: true, direction: "center", className: "ggc-zone" })
    .addTo(zoneLayer!);
}

function textNode(text: string): HTMLElement {
  const span = document.createElement("span");
  span.textContent = text;
  return span;
}

/** Ta ville choisie (marqueur) et les lieux lus que tes choix écartent (grisés, jamais effacés). */
function drawChoices() {
  if (!placeLayer) return;
  for (const o of outside.value) {
    L.circleMarker([o.lat, o.lon], { radius: 4, color: COLORS.courbe, weight: 1.5, fillColor: COLORS.courbeFonce, fillOpacity: 1 })
      .bindTooltip(textNode(`${circled(o.n)} ${o.label} · hors de ton choix`),
                   { permanent: true, direction: "right", className: "ggc-zone ggc-place ggc-outside" })
      .addTo(placeLayer);
  }
  const city = lockCity.value;
  if (city?.lat != null && city.lon != null) {
    L.circleMarker([city.lat, city.lon], { radius: 8, color: COLORS.marque, weight: 3, fillColor: COLORS.encre, fillOpacity: 1 })
      .bindTooltip(textNode(`${city.name} (${city.by === "user" ? "toi" : "le coach"})`),
                   { permanent: true, direction: "top", className: "ggc-zone" })
      .addTo(placeLayer);
  }
}

function drawLocation() {
  const loc = location.value;
  if (!loc || !placeLayer) return;
  if (loc.kind === "point") {
    L.circle([loc.lat, loc.lon], {
      radius: loc.radius_km * 1000, color: COLORS.marque, weight: 2, fillColor: COLORS.marque, fillOpacity: 0.18,
      interactive: false,
    }).bindTooltip(`Ici, à ${fr(loc.radius_km)} km près`, { permanent: true, direction: "top", className: "ggc-zone" })
      .addTo(placeLayer);
  } else if (loc.kind === "rough") {
    L.circle([loc.lat, loc.lon], {
      radius: loc.radius_km * 1000, color: COLORS.marque, weight: 1.5, dashArray: "3 5", fillColor: COLORS.marque,
      fillOpacity: 0.08, interactive: false,
    }).addTo(placeLayer);
  } else if (loc.kind === "ring") {
    L.circle([loc.lat, loc.lon], {
      radius: loc.radius_km * 1000, color: COLORS.marque, weight: 2, dashArray: "6 4", fillOpacity: 0, interactive: false,
    }).addTo(placeLayer);
  }
  for (const p of loc.places) {
    L.circleMarker([p.lat, p.lon], { radius: 4, color: COLORS.encre, weight: 1.5, fillColor: COLORS.marque, fillOpacity: 1 })
      // Texte lu par l'IA : en nœud texte, jamais en HTML (Leaflet insère une chaîne comme du HTML).
      .bindTooltip(textNode(`${circled(p.n)} ${p.name}${p.km ? ` · ${fr(p.km)} km` : ""}`),
                   { permanent: true, direction: "right", className: "ggc-zone ggc-place" })
      .addTo(placeLayer);
  }
}

function redraw() {
  if (!map) return;
  outlines?.setStyle((f) => styleFor(codeOf(f)));
  zoneLayer?.clearLayers();
  placeLayer?.clearLayers();
  zones.value.forEach(drawZone);
  drawChoices();
  drawLocation();
  const bounds = frame();
  if (bounds?.isValid()) {
    // Une position estimée se regarde de près (rues, villages) ; une zone ou un pays, de loin.
    // Lieux lus, ville ou région choisies : cadrés au plus près (fitBounds s'arrête là où ils tiennent tous).
    const close = !!(location.value || lockCity.value || regionBounds.value);
    const options = { padding: [24, 24] as L.PointTuple, maxZoom: close ? engine.map.max_zoom : Math.min(engine.map.max_zoom, 8) };
    if (reducedMotion) map.fitBounds(bounds, options);
    else map.flyToBounds(bounds, { ...options, duration: 0.8 });
  }
}

onMounted(async () => {
  if (!el.value) return;
  map = L.map(el.value, {
    attributionControl: false, // attribution affichée par le coach, toujours visible (règles OSM)
    worldCopyJump: true,
    minZoom: 1,
    maxZoom: engine.map.max_zoom,
  }).setView([25, 10], 1);
  // Sombre de loin (pays, zones), presque d'origine de près (rues, villages) : l'inversion y devient illisible.
  const tiles = map.getPane("tilePane")!;
  if (!reducedMotion) tiles.style.transition = "filter 250ms ease-out";
  const applyFilter = () => {
    tiles.style.filter = (map?.getZoom() ?? 0) >= engine.map.close_zoom ? engine.map.tile_filter_close : engine.map.tile_filter;
  };
  const applyLabels = () => el.value?.classList.toggle("ggc-far", (map?.getZoom() ?? 0) < LABELS_ZOOM);
  applyFilter();
  applyLabels();
  map.on("zoomend", () => {
    applyFilter();
    applyLabels();
  });
  L.tileLayer(engine.map.tile_url, { maxZoom: engine.map.max_zoom }).addTo(map);
  resize = new ResizeObserver(() => map?.invalidateSize()); // fenêtre redimensionnée
  resize.observe(el.value);
  const geo = await countryOutlines();
  if (!map) return; // carte démontée pendant le chargement
  if (geo) outlines = L.geoJSON(geo, { style: (f) => styleFor(codeOf(f)), interactive: false }).addTo(map);
  else outlinesMissing.value = true;
  zoneLayer = L.layerGroup().addTo(map); // après les pays : les zones passent par-dessus
  placeLayer = L.layerGroup().addTo(map); // puis les lieux lus sur tes marques, au-dessus de tout
  redraw();
});

watch(
  () => [props.analysis.scores, props.analysis.cloud, head.value?.code, certain.value?.country, props.level, location.value,
         props.analysis.locks, outside.value],
  () => redraw(),
);

onBeforeUnmount(() => {
  resize?.disconnect();
  map?.remove();
  map = null;
});
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <div class="relative min-h-80 flex-1 overflow-hidden rounded-md border border-courbe-fonce">
      <div ref="el" class="absolute inset-0 bg-encre" role="img" aria-label="Carte des pays probables et des zones probables" />
      <button
        type="button"
        class="absolute right-0 bottom-0 z-[1000] rounded-tl bg-encre/85 px-1.5 py-0.5 text-[0.7rem] text-courbe hover:text-papier"
        @click="openAttribution"
      >
        {{ engine.map.attribution }}
      </button>
    </div>

    <!-- Ce qui est sûr : la carte se cadre dessus (la région d'après l'étendue de ses lieux, sans contour). -->
    <p v-if="lockCountry" class="mt-3 text-papier">
      <span class="text-courbe">C'est sûr :</span> {{ flag(lockCountry.country) }} {{ countryName(lockCountry.country) }}
      <template v-if="lockRegion"> › {{ lockRegion.name }}</template>
      <template v-if="lockCity"> › {{ lockCity.name }}</template>
      <span v-if="lockRegion && !lockCity" class="text-[0.85rem] text-courbe"> (cadrée sur l'étendue de ses lieux, sans contour)</span>
    </p>
    <p v-if="outside.length" class="mt-1 text-[0.85rem] text-courbe">
      Grisés : {{ outside.map((o) => `${circled(o.n)} ${o.label}`).join(", ") }}, lus mais hors de ton choix.
    </p>

    <!-- Tes marques situent la vue : lieux lus (GeoNames) et distances d'un panneau directionnel. -->
    <section v-if="location" class="mt-3" aria-labelledby="position-titre">
      <h2 id="position-titre" class="font-bold text-papier">
        <span class="mr-1.5 inline-block size-2.5 rounded-full bg-marque align-middle" aria-hidden="true" />
        {{ location.kind === "places" ? "Lieux lus sur tes marques" : "Position estimée d'après tes marques" }}
      </h2>
      <p v-if="location.kind === 'rough'" class="border-l-2 border-alerte/70 pl-3 text-[0.9rem] text-papier">
        Distances incohérentes entre elles : vérifie
        {{ location.doubtful.map((d) => `${circled(d.n)} ${d.name} ${fr(d.km)} km`).join(", ") }}. Un chiffre mal lu
        donnerait une fausse précision ; sûr malgré tout : la vue est à moins de {{ fr(location.radius_km) }} km de
        {{ nearestRead?.name ?? "ce lieu" }}.
      </p>
      <p v-if="location.kind === 'point'" class="text-papier">
        {{ coords(location.lat, location.lon) }} <span class="text-courbe">· à {{ fr(location.radius_km) }} km près</span>
      </p>
      <p v-else-if="location.kind === 'ring'" class="text-papier">
        À environ {{ fr(location.radius_km) }} km à vol d'oiseau de {{ location.places.find((p) => p.km)?.name }}
        <span class="text-courbe">(un seul lieu avec sa distance : la vue est quelque part sur ce cercle)</span>
      </p>
      <p class="mt-1 text-[0.85rem] text-courbe">
        <template v-if="distances.length">
          Distances lues : {{ distances.map((p) => `${circled(p.n)} ${p.name} ${fr(p.km!)} km`).join(", ") }}. Ce sont des
          distances par la route : le coach les convertit à vol d'oiseau (détour ×1,15 à ×1,45), d'où la marge.
        </template>
        <template v-else>
          {{ location.places.map((p) => `${circled(p.n)} ${p.name}`).join(", ") }} : la vue est dans leurs parages
          (sans distance lue, pas de position plus précise).
        </template>
        Lieux : GeoNames.
      </p>
    </section>

    <section class="mt-3" aria-labelledby="zones-titre">
      <h2 id="zones-titre" class="font-bold text-papier">
        {{ head && analysis.cloud.status === "done" && analysis.cloud.data.zones_by_country[head.code]
          ? `Zones probables en ${countryName(head.code)}${head.certain ? "" : head.source === "marks" ? " (tes marques)" : " (lu par l'IA, à confirmer)"}`
          : "Zones probables" }}
      </h2>
      <p v-if="head && !head.certain && analysis.cloud.status === 'done' && !analysis.cloud.data.zones_by_country[head.code]"
         class="text-[0.85rem] text-courbe">
        Presque aucune position ne tombe en {{ countryName(head.code) }} : voici les zones de tous les pays.
      </p>
      <ol v-if="zones.length" class="mt-1.5 space-y-1">
        <li v-for="(z, i) in zones" :key="i" class="grid grid-cols-[1.5rem_1fr_auto] items-baseline gap-2">
          <span class="text-courbe tabular-nums">{{ i + 1 }}.</span>
          <span class="text-papier">
            <template v-for="([code, part], j) in z.countries" :key="code">
              <template v-if="j"> et </template>{{ flag(code) }} {{ countryName(code) }}<span v-if="z.countries.length > 1" class="text-courbe"> ({{ pct(part) }})</span>
            </template>
            <span v-if="!z.countries.length" class="text-courbe">surtout en mer</span>
            <span class="text-courbe"> · ~{{ roundKm(z.width_km) }} × {{ roundKm(z.height_km) }} km</span>
          </span>
          <span class="text-right tabular-nums text-courbe">{{ pct(z.part) }} des positions</span>
        </li>
      </ol>
      <p v-else class="mt-1 text-[0.85rem] text-courbe">
        <template v-if="zonesHidden">
          Masquées : elles ne viennent que de l'allure de la vue, et tes marques situent la vue bien plus précisément.
        </template>
        <template v-else-if="analysis.cloud.status === 'pending'">Calcul des zones…</template>
        <template v-else-if="analysis.cloud.status === 'error'">{{ analysis.cloud.error }} : la carte montre les pays seulement.</template>
        <template v-else-if="analysis.cloud.status === 'done' && certain">
          Presque aucune position ne tombe en {{ countryName(certain.country) }} : la carte montre le pays prouvé.
        </template>
        <template v-else-if="analysis.cloud.status === 'done'">Pas de zone nette : les positions sont trop dispersées.</template>
        <template v-else-if="engine.plonk.enabled">Zones indisponibles (PLONK : {{ engine.plonk.message }}).</template>
        <template v-else>Zones désactivées dans les réglages : la carte montre les pays seulement.</template>
      </p>
      <p class="mt-2 text-[0.8rem] text-courbe">
        Une piste, pas une preuve : les zones viennent de la même allure de vue que StreetCLIP (modèle PLONK) et
        tombent en général à 100–300 km du lieu quand le pays est juste.
        <template v-if="outlinesMissing"> Contours des pays indisponibles.</template>
      </p>
    </section>
  </div>
</template>
