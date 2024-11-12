console.log('dashboard.js loaded');

// colors to use for the categories
// soft green, yellow, red
const visitColors = ['#4ade80', '#fbbf24', '#f87171'];

// Function to create a donut chart
function createDonutChart(props, map) {
  console.log('createDonutChart', props);
  const offsets = [];
  const counts = [props.approved, props.pending, props.rejected];
  let total = 0;
  for (const count of counts) {
    offsets.push(total);
    total += count;
  }
  const fontSize =
    total >= 1000 ? 22 : total >= 100 ? 20 : total >= 10 ? 18 : 16;
  const r = total >= 1000 ? 50 : total >= 100 ? 32 : total >= 10 ? 24 : 18;
  const r0 = Math.round(r * 0.8);
  const w = r * 2;

  let html = `<div>
        <svg width="${w}" height="${w}" viewbox="0 0 ${w} ${w}" text-anchor="middle" style="font: ${fontSize}px sans-serif; display: block">
        <defs>
          <filter id="shadow">
            <feDropShadow dx="0" dy="1" stdDeviation="2" flood-opacity="0.3"/>
          </filter>
        </defs>`;

  for (let i = 0; i < counts.length; i++) {
    html += donutSegment(
      offsets[i] / total,
      (offsets[i] + counts[i]) / total,
      r,
      r0,
      visitColors[i],
    );
  }
  html += `<circle cx="${r}" cy="${r}" r="${r0}" fill="#374151" />
        <text dominant-baseline="central" transform="translate(${r}, ${r})"
              fill="white" font-weight="500" filter="url(#shadow)">
            ${total.toLocaleString()}
        </text>
        </svg>
        </div>`;

  const el = document.createElement('div');
  el.innerHTML = html;
  el.style.cursor = 'pointer';

  // Click handler to zoom and navigate to the cluster
  el.addEventListener('click', (e) => {
    map
      .getSource('visits')
      .getClusterExpansionZoom(props.cluster_id, (err, zoom) => {
        if (err) return;

        map.easeTo({
          center: props.coordinates,
          zoom: zoom,
        });
      });
  });

  return el;
}

// Function to create a donut segment
function donutSegment(start, end, r, r0, color) {
  if (end - start === 1) end -= 0.00001;
  const a0 = 2 * Math.PI * (start - 0.25);
  const a1 = 2 * Math.PI * (end - 0.25);
  const x0 = Math.cos(a0),
    y0 = Math.sin(a0);
  const x1 = Math.cos(a1),
    y1 = Math.sin(a1);
  const largeArc = end - start > 0.5 ? 1 : 0;

  // draw an SVG path
  return `<path d="M ${r + r0 * x0} ${r + r0 * y0} L ${r + r * x0} ${
    r + r * y0
  } A ${r} ${r} 0 ${largeArc} 1 ${r + r * x1} ${r + r * y1} L ${r + r0 * x1} ${
    r + r0 * y1
  } A ${r0} ${r0} 0 ${largeArc} 0 ${r + r0 * x0} ${
    r + r0 * y0
  }" fill="${color}" opacity="0.85" stroke="#1f2937" stroke-width="1" />`;
}

window.createDonutChart = createDonutChart;
