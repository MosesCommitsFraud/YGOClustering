import os
import json
import itertools
import requests
from collections import Counter
import networkx as nx
import community as community_louvain  # Louvain community detection

# -----------------------
# Step 1: Download Card Data
# -----------------------
CARDINFO_FILENAME = "cardinfo.json"
API_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"

if not os.path.exists(CARDINFO_FILENAME):
    print("Downloading card data from API...")
    response = requests.get(API_URL)
    response.raise_for_status()
    card_data = response.json()
    with open(CARDINFO_FILENAME, "w", encoding="utf-8") as f:
        json.dump(card_data, f, ensure_ascii=False, indent=4)
else:
    print("Loading card data from local file...")
    with open(CARDINFO_FILENAME, "r", encoding="utf-8") as f:
        card_data = json.load(f)

# Build lookup dictionary: card id (as string) -> card info
card_info = {}
for card in card_data.get("data", []):
    card_id_str = str(card["id"])
    card_info[card_id_str] = card

# -----------------------
# Step 2: Process YDK Files for Statistics & Co-occurrence
# -----------------------
YDK_FOLDER = r"C:\Users\morit\Documents\ydk_download"
ydk_files = [f for f in os.listdir(YDK_FOLDER) if f.endswith(".ydk")]

card_stats = {}  # { card_id: {"total": count, "main": count, "extra": count, "side": count} }
edge_counter = Counter()  # {(card_a, card_b): count}

print("Processing YDK files...")
for filename in ydk_files:
    filepath = os.path.join(YDK_FOLDER, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    deck = {"main": [], "extra": [], "side": []}
    current_section = None
    for line in lines:
        line = line.strip()
        if line.startswith('#'):
            if "main" in line.lower():
                current_section = "main"
            elif "extra" in line.lower():
                current_section = "extra"
            elif "side" in line.lower():
                current_section = "side"
            else:
                current_section = None
        elif line.startswith('!'):
            if "side" in line.lower():
                current_section = "side"
        elif line and line.isdigit() and current_section:
            deck[current_section].append(line)

    for section, card_list in deck.items():
        for card in card_list:
            if card not in card_stats:
                card_stats[card] = {"total": 0, "main": 0, "extra": 0, "side": 0}
            card_stats[card]["total"] += 1
            card_stats[card][section] += 1

    unique_cards = set(deck["main"] + deck["extra"] + deck["side"])
    for card_a, card_b in itertools.combinations(sorted(unique_cards), 2):
        edge_counter[(card_a, card_b)] += 1

print("Finished processing decks.")
unused_cards = [cid for cid in card_info.keys() if cid not in card_stats]
print(f"Total cards in API: {len(card_info)}")
print(f"Cards that never appeared in a deck: {len(unused_cards)}")

# -----------------------
# Step 3: Build a NetworkX Graph, Filter, and Precompute Layout
# -----------------------
EDGE_THRESHOLD = 0  # Adjust to filter out low-frequency edges

G = nx.Graph()
for (card_a, card_b), weight in edge_counter.items():
    if weight >= EDGE_THRESHOLD:
        G.add_edge(card_a, card_b, weight=weight)
for card_id in card_stats.keys():
    if card_id not in G:
        G.add_node(card_id)

# Use the Louvain algorithm to detect communities.
# This returns a dictionary mapping each node to a community id.
node2community = community_louvain.best_partition(G)

# Define a color palette.
colors = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4",
    "#46f0f0", "#f032e6", "#bcf60c", "#fabebe", "#008080", "#e6beff",
    "#9a6324", "#fffac8", "#800000", "#aaffc3", "#808000", "#ffd8b1",
    "#000075", "#808080", "#ffffff", "#000000"
]

# Compute node positions using spring layout.
print("Computing layout with NetworkX...")
# Increase k and iterations for more separation if needed.
pos = nx.spring_layout(G, k=0.25, iterations=100)
scale = 4000  # Increased scale factor for more space

# -----------------------
# Step 4: Prepare Cytoscape.js Graph Data
# -----------------------
cy_nodes = []
for card_id, stats in card_stats.items():
    card = card_info.get(card_id, {})
    name = card.get("name", card_id)
    x, y = pos.get(card_id, (0, 0))
    size = max(5, min(20, stats["total"] / 5))
    community_id = node2community.get(card_id, 0)
    color = colors[community_id % len(colors)]
    title = f"Total: {stats['total']}<br>Main: {stats['main']}<br>Extra: {stats['extra']}<br>Side: {stats['side']}"
    cy_nodes.append({
        "data": {
            "id": card_id,
            "label": name,
            "title": title,
            "size": size,
            "color": color
        },
        "position": {
            "x": x * scale,
            "y": y * scale
        }
    })

cy_edges = []
edge_id = 0
for (card_a, card_b), weight in edge_counter.items():
    if weight >= EDGE_THRESHOLD:
        comm_a = node2community.get(card_a, -1)
        comm_b = node2community.get(card_b, -1)
        if comm_a == comm_b and comm_a != -1:
            edge_color = colors[comm_a % len(colors)]
        else:
            edge_color = "#AAAAAA"
        cy_edges.append({
            "data": {
                "id": f"e{edge_id}",
                "source": card_a,
                "target": card_b,
                "weight": weight,
                "title": f"Co-occurrence: {weight}",
                "color": edge_color
            }
        })
        edge_id += 1

cy_elements = {
    "nodes": cy_nodes,
    "edges": cy_edges
}

# -----------------------
# Step 5: Write HTML File that Uses Cytoscape.js
# -----------------------
html_template = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Yu-Gi-Oh! Card Cluster Visualization with Cytoscape.js</title>
  <style>
    html, body {{ width: 100%; height: 100%; margin: 0; padding: 0; }}
    #cy {{ width: 100%; height: 100%; position: absolute; left: 0; top: 0; }}
  </style>
  <!-- Load Cytoscape.js from CDN -->
  <script src="https://unpkg.com/cytoscape@3.23.0/dist/cytoscape.min.js"></script>
</head>
<body>
  <div id="cy"></div>
  <script>
    // Parse the graph data from Python
    var elements = {json.dumps(cy_elements)};

    // Initialize Cytoscape with the "preset" layout to use our precomputed positions
    var cy = cytoscape({{
      container: document.getElementById('cy'),
      elements: elements,
      style: [
        {{
          selector: 'node',
          style: {{
            'label': 'data(label)',
            'background-color': 'data(color)',
            'width': 'data(size)',
            'height': 'data(size)',
            'text-valign': 'center',
            'color': '#fff',
            'font-size': '4px',
            'text-outline-width': 1,
            'text-outline-color': '#000'
          }}
        }},
        {{
          selector: 'edge',
          style: {{
            'width': 1,
            'line-color': 'data(color)',
            'curve-style': 'bezier',
            'opacity': 0.8
          }}
        }}
      ],
      layout: {{
        name: 'preset'
      }}
    }});
  </script>
</body>
</html>
"""

output_file = "cytoscape_network.html"
with open(output_file, "w", encoding="utf-8") as f:
    f.write(html_template)

print(f"Cytoscape.js network HTML saved to {output_file}.")
