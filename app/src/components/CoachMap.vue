<script setup lang="ts">
// Map tab (level 3 and up): likely countries coloured by StreetCLIP, countries greyed out when ruled out by
// strong proof, and the ZONES where the view probably is (PLONK positions grouped by the engine).
// At level 4, strong proof zooms onto its country. The PLACES READ on your marks are plotted (GeoNames), and
// a direction sign's distances give an estimated position within a few km: it takes precedence over the zones.
// Online OpenStreetMap background, darkened by a CSS filter; offline, countries, zones and places are still drawn.
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
/** Leading country: proven, or read by the AI (very likely, the others stay coloured). */
const head = computed(() => headCountry(props.analysis));
/** PLONK zones (look of the view): hidden as soon as your marks locate the view, far more precisely. */
const zones = computed(() => (props.analysis.verdict?.location ? [] : visibleZones(props.analysis)));
const zonesHidden = computed(() => !!props.analysis.verdict?.location && visibleZones(props.analysis).length > 0);
const LABELS_ZOOM = 9; // below this, the names of the places read overlap: only the dots remain
/** Position estimated from your marks (places read, distances on a sign). */
const location = computed(() => props.analysis.verdict?.location ?? null);
const coords = (lat: number, lon: number) =>
  `${lat.toFixed(4).replace(".", ",")}° ${lat >= 0 ? "N" : "S"}, ${lon.toFixed(4).replace(".", ",")}° ${lon >= 0 ? "E" : "O"}`;
const distances = computed(() => location.value?.places.filter((p) => p.km) ?? []);
/** Closest place read (smallest distance on the sign). */
const nearestRead = computed(() => [...distances.value].sort((a, b) => a.km! - b.km!)[0] ?? null);
// What is certain (your choices, or the coach's at the level that reveals them): the map frames it.
const shownLock = (l?: Lock) => (l && (l.by === "user" || props.level >= (l.level === "country" ? 3 : 4)) ? l : null);
const lockCountry = computed(() => shownLock(props.analysis.locks?.held.country));
const lockRegion = computed(() => shownLock(props.analysis.locks?.held.region));
const lockCity = computed(() => shownLock(props.analysis.locks?.held.city));
const regionBounds = computed(() => (lockRegion.value ? props.analysis.locks?.region_bounds ?? null : null));
const outside = computed(() => props.analysis.verdict?.outside ?? []);
const probability = (code: string) => props.analysis.scores?.find((s) => s.code === code)?.probability ?? 0;
const pct = (p: number) => `${Math.round(p * 100)} %`;
/** Readable size: rounded to 10 km, to 50 km beyond 200 km. */
const roundKm = (km: number) => {
  const step = km > 200 ? 50 : 10;
  return Math.max(10, Math.round(km / step) * step);
};

function styleFor(code: string): L.PathOptions {
  const proven = certain.value?.country ?? lockCountry.value?.country; // proven, or stated as certain
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
  return L.latLng(loc.lat, loc.lon).toBounds(loc.radius_km * 2000 * 1.6); // the circle and a bit of surroundings
}

function frame(): L.LatLngBounds | null {
  const city = lockCity.value;
  if (city?.lat != null && city.lon != null) return L.latLng(city.lat, city.lon).toBounds(5000); // the chosen city
  const here = locationBounds(); // your marks locate the view: more precise than everything else
  if (here) return here;
  const rb = regionBounds.value; // the chosen region, from the extent of its places
  if (rb) return L.latLngBounds([rb[0], rb[1]], [rb[2], rb[3]]).pad(0.05);
  if (lockCountry.value) return countryBounds(lockCountry.value.country);
  const top = head.value?.code;
  if (props.level >= 4 && top) return countryBounds(top); // the answer: zoom in on the leading country
  if (zones.value.length) return union(zones.value.map((z) => L.latLngBounds(z.polygon)));
  // Without a zone: the likely countries (above 5 %, three at most).
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

/** Your chosen city (marker) and the places read that your choices rule out (greyed out, never erased). */
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
      // Text read by the AI: as a text node, never as HTML (Leaflet inserts a string as HTML).
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
    // An estimated position is looked at up close (streets, villages); a zone or a country, from afar.
    // Places read, chosen city or region: framed as tightly as possible (fitBounds stops where they all fit).
    const close = !!(location.value || lockCity.value || regionBounds.value);
    const options = { padding: [24, 24] as L.PointTuple, maxZoom: close ? engine.map.max_zoom : Math.min(engine.map.max_zoom, 8) };
    if (reducedMotion) map.fitBounds(bounds, options);
    else map.flyToBounds(bounds, { ...options, duration: 0.8 });
  }
}

onMounted(async () => {
  if (!el.value) return;
  map = L.map(el.value, {
    attributionControl: false, // attribution shown by the coach, always visible (OSM rules)
    worldCopyJump: true,
    minZoom: 1,
    maxZoom: engine.map.max_zoom,
  }).setView([25, 10], 1);
  // Dark from afar (countries, zones), near original up close (streets, villages): inversion is unreadable there.
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
  resize = new ResizeObserver(() => map?.invalidateSize()); // window resized
  resize.observe(el.value);
  const geo = await countryOutlines();
  if (!map) return; // map unmounted during loading
  if (geo) outlines = L.geoJSON(geo, { style: (f) => styleFor(codeOf(f)), interactive: false }).addTo(map);
  else outlinesMissing.value = true;
  zoneLayer = L.layerGroup().addTo(map); // after the countries: the zones go on top
  placeLayer = L.layerGroup().addTo(map); // then the places read on your marks, above everything
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

    <!-- What is certain: the map frames it (the region from the extent of its places, without an outline). -->
    <p v-if="lockCountry" class="mt-3 text-papier">
      <span class="text-courbe">C'est sûr :</span> {{ flag(lockCountry.country) }} {{ countryName(lockCountry.country) }}
      <template v-if="lockRegion"> › {{ lockRegion.name }}</template>
      <template v-if="lockCity"> › {{ lockCity.name }}</template>
      <span v-if="lockRegion && !lockCity" class="text-[0.85rem] text-courbe"> (cadrée sur l'étendue de ses lieux, sans contour)</span>
    </p>
    <p v-if="outside.length" class="mt-1 text-[0.85rem] text-courbe">
      Grisés : {{ outside.map((o) => `${circled(o.n)} ${o.label}`).join(", ") }}, lus mais hors de ton choix.
    </p>

    <!-- Your marks locate the view: places read (GeoNames) and distances on a direction sign. -->
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
