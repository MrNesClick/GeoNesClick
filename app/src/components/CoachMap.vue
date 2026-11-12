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
import { certainProof, circled, countryName, countryOutlines, engine, flag, num, headCountry, openAttribution, visibleZones } from "../engine";
import { i18n, pct, t } from "../i18n";

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
const deg = (x: number) => x.toLocaleString(i18n.lang, { minimumFractionDigits: 4, maximumFractionDigits: 4 });
const coords = (lat: number, lon: number) =>
  `${deg(lat)}° ${t(lat >= 0 ? "coord.north" : "coord.south")}, ${deg(lon)}° ${t(lon >= 0 ? "coord.east" : "coord.west")}`;
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
    .bindTooltip(`${rank + 1} · ${pct(zone.part)}`, { permanent: true, direction: "center", className: "map-zone" })
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
      .bindTooltip(textNode(t("map.outside_choice", { place: `${circled(o.n)} ${o.label}` })),
                   { permanent: true, direction: "right", className: "map-zone map-place map-outside" })
      .addTo(placeLayer);
  }
  const city = lockCity.value;
  if (city?.lat != null && city.lon != null) {
    L.circleMarker([city.lat, city.lon], { radius: 8, color: COLORS.marque, weight: 3, fillColor: COLORS.encre, fillOpacity: 1 })
      .bindTooltip(textNode(`${city.name} (${t(city.by === "user" ? "locks.by_you" : "locks.by_coach")})`),
                   { permanent: true, direction: "top", className: "map-zone" })
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
    }).bindTooltip(textNode(t("map.here_within", { km: num(loc.radius_km) })), { permanent: true, direction: "top", className: "map-zone" })
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
      .bindTooltip(textNode(`${circled(p.n)} ${p.name}${p.km ? ` · ${num(p.km)} km` : ""}`),
                   { permanent: true, direction: "right", className: "map-zone map-place" })
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
  const applyLabels = () => el.value?.classList.toggle("map-far", (map?.getZoom() ?? 0) < LABELS_ZOOM);
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
         props.analysis.locks, outside.value, i18n.lang], // the tooltips are drawn once: a language change redraws them
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
      <div ref="el" class="absolute inset-0 bg-encre" role="img" :aria-label="t('map.aria')" />
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
      <span class="text-courbe">{{ t("locks.sure") }}</span> {{ flag(lockCountry.country) }} {{ countryName(lockCountry.country) }}
      <template v-if="lockRegion"> › {{ lockRegion.name }}</template>
      <template v-if="lockCity"> › {{ lockCity.name }}</template>
      <span v-if="lockRegion && !lockCity" class="text-[0.85rem] text-courbe">{{ t("map.region_framed") }}</span>
    </p>
    <p v-if="outside.length" class="mt-1 text-[0.85rem] text-courbe">
      {{ t("map.greyed", { places: outside.map((o) => `${circled(o.n)} ${o.label}`).join(", ") }) }}
    </p>

    <!-- Your marks locate the view: places read (GeoNames) and distances on a direction sign. -->
    <section v-if="location" class="mt-3" aria-labelledby="position-title">
      <h2 id="position-title" class="font-bold text-papier">
        <span class="mr-1.5 inline-block size-2.5 rounded-full bg-marque align-middle" aria-hidden="true" />
        {{ t(location.kind === "places" ? "map.places_read" : "map.position_estimated") }}
      </h2>
      <p v-if="location.kind === 'rough'" class="border-l-2 border-alerte/70 pl-3 text-[0.9rem] text-papier">
        {{ t("map.rough", { doubtful: location.doubtful.map((d) => `${circled(d.n)} ${d.name} ${num(d.km)} km`).join(", "),
                            km: num(location.radius_km), place: nearestRead?.name ?? t("map.this_place") }) }}
      </p>
      <p v-if="location.kind === 'point'" class="text-papier">
        {{ coords(location.lat, location.lon) }} <span class="text-courbe">{{ t("map.within", { km: num(location.radius_km) }) }}</span>
      </p>
      <p v-else-if="location.kind === 'ring'" class="text-papier">
        {{ t("map.ring", { km: num(location.radius_km), place: location.places.find((p) => p.km)?.name ?? "" }) }}
        <span class="text-courbe">{{ t("map.ring_note") }}</span>
      </p>
      <p class="mt-1 text-[0.85rem] text-courbe">
        <template v-if="distances.length">
          {{ t("map.distances", { list: distances.map((p) => `${circled(p.n)} ${p.name} ${num(p.km!)} km`).join(", ") }) }}
        </template>
        <template v-else>
          {{ t("map.nearby", { list: location.places.map((p) => `${circled(p.n)} ${p.name}`).join(", ") }) }}
        </template>
        {{ t("map.places_source") }}
      </p>
    </section>

    <section class="mt-3" aria-labelledby="zones-title">
      <h2 id="zones-title" class="font-bold text-papier">
        {{ head && analysis.cloud.status === "done" && analysis.cloud.data.zones_by_country[head.code]
          ? t("map.zones_in", { country: countryName(head.code),
                                why: head.certain ? "" : t(head.source === "marks" ? "map.zones_why_marks" : "map.zones_why_ai") })
          : t("map.zones") }}
      </h2>
      <p v-if="head && !head.certain && analysis.cloud.status === 'done' && !analysis.cloud.data.zones_by_country[head.code]"
         class="text-[0.85rem] text-courbe">
        {{ t("map.almost_none_in", { country: countryName(head.code) }) }}
      </p>
      <ol v-if="zones.length" class="mt-1.5 space-y-1">
        <li v-for="(z, i) in zones" :key="i" class="grid grid-cols-[1.5rem_1fr_auto] items-baseline gap-2">
          <span class="text-courbe tabular-nums">{{ i + 1 }}.</span>
          <span class="text-papier">
            <template v-for="([code, part], j) in z.countries" :key="code">
              <template v-if="j">{{ t("map.and") }}</template>{{ flag(code) }} {{ countryName(code) }}<span v-if="z.countries.length > 1" class="text-courbe"> ({{ pct(part) }})</span>
            </template>
            <span v-if="!z.countries.length" class="text-courbe">{{ t("map.mostly_sea") }}</span>
            <span class="text-courbe"> · ~{{ roundKm(z.width_km) }} × {{ roundKm(z.height_km) }} km</span>
          </span>
          <span class="text-right tabular-nums text-courbe">{{ t("map.of_positions", { pct: pct(z.part) }) }}</span>
        </li>
      </ol>
      <p v-else class="mt-1 text-[0.85rem] text-courbe">
        <template v-if="zonesHidden">
          {{ t("map.hidden") }}
        </template>
        <template v-else-if="analysis.cloud.status === 'pending'">{{ t("map.computing") }}</template>
        <template v-else-if="analysis.cloud.status === 'error'">{{ t("map.error", { error: analysis.cloud.error }) }}</template>
        <template v-else-if="analysis.cloud.status === 'done' && certain">
          {{ t("map.almost_none_proven", { country: countryName(certain.country) }) }}
        </template>
        <template v-else-if="analysis.cloud.status === 'done'">{{ t("map.scattered") }}</template>
        <template v-else-if="engine.plonk.enabled">{{ t("map.unavailable", { message: engine.plonk.message }) }}</template>
        <template v-else>{{ t("map.off") }}</template>
      </p>
      <p class="mt-2 text-[0.8rem] text-courbe">
        {{ t("map.lead") }}<template v-if="outlinesMissing">{{ t("map.outlines_missing") }}</template>
      </p>
    </section>
  </div>
</template>
