<script setup lang="ts">
// Onglet Carte (niveau 3 et plus) : pays probables colorés selon StreetCLIP, pays écartés grisés par une
// preuve forte, et les ZONES où la vue se trouve probablement (positions PLONK regroupées par le moteur).
// Au niveau 4, une preuve forte recadre sur son pays. Fond OpenStreetMap en ligne, assombri par un filtre
// CSS ; sans réseau, pays et zones restent dessinés.
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { Analysis, Zone } from "../engine";
import { certainProof, countryName, countryOutlines, engine, flag, openAttribution, visibleZones } from "../engine";

const props = defineProps<{ analysis: Analysis; level: number }>();

const el = ref<HTMLDivElement | null>(null);
const outlinesMissing = ref(false);
let map: L.Map | null = null;
let outlines: L.GeoJSON | null = null;
let zoneLayer: L.LayerGroup | null = null;
let resize: ResizeObserver | null = null;

const css = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
const COLORS = {
  foret: css("--color-foret", "#7db38a"),
  lac: css("--color-lac", "#7fb6d6"),
  courbe: css("--color-courbe", "#8a9aa6"),
  courbeFonce: css("--color-courbe-fonce", "#2b3d4f"),
  encre: css("--color-encre", "#15202b"),
};
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const certain = computed(() => certainProof(props.analysis));
const zones = computed(() => visibleZones(props.analysis));
const probability = (code: string) => props.analysis.scores?.find((s) => s.code === code)?.probability ?? 0;
const pct = (p: number) => `${Math.round(p * 100)} %`;
/** Taille lisible : arrondie à 10 km, à 50 km au-delà de 200 km. */
const roundKm = (km: number) => {
  const step = km > 200 ? 50 : 10;
  return Math.max(10, Math.round(km / step) * step);
};

function styleFor(code: string): L.PathOptions {
  const proven = certain.value?.country;
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

function frame(): L.LatLngBounds | null {
  const proven = certain.value?.country;
  if (props.level >= 4 && proven) return countryBounds(proven); // la réponse : on resserre sur le pays prouvé
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

function redraw() {
  if (!map) return;
  outlines?.setStyle((f) => styleFor(codeOf(f)));
  zoneLayer?.clearLayers();
  zones.value.forEach(drawZone);
  const bounds = frame();
  if (bounds?.isValid()) {
    const options = { padding: [24, 24] as L.PointTuple, maxZoom: Math.min(engine.map.max_zoom, 8) };
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
  map.getPane("tilePane")!.style.filter = engine.map.tile_filter;
  L.tileLayer(engine.map.tile_url, { maxZoom: engine.map.max_zoom }).addTo(map);
  resize = new ResizeObserver(() => map?.invalidateSize()); // fenêtre redimensionnée
  resize.observe(el.value);
  const geo = await countryOutlines();
  if (!map) return; // carte démontée pendant le chargement
  if (geo) outlines = L.geoJSON(geo, { style: (f) => styleFor(codeOf(f)), interactive: false }).addTo(map);
  else outlinesMissing.value = true;
  zoneLayer = L.layerGroup().addTo(map); // après les pays : les zones passent par-dessus
  redraw();
});

watch(
  () => [props.analysis.scores, props.analysis.cloud, certain.value?.country, props.level],
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

    <section class="mt-3" aria-labelledby="zones-titre">
      <h2 id="zones-titre" class="font-bold text-papier">
        {{ certain ? `Zones probables en ${countryName(certain.country)}` : "Zones probables" }}
      </h2>
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
        <template v-if="analysis.cloud.status === 'pending'">Calcul des zones…</template>
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
