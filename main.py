import os
import json
import itertools
import requests
from collections import Counter
from pyvis.network import Network

# ----- Step 1: Get card information (download once locally) -----
CARDINFO_FILENAME = "cardinfo.json"
API_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"

if not os.path.exists(CARDINFO_FILENAME):
    print("Downloading card data from API...")
    response = requests.get(API_URL)
    response.raise_for_status()  # raise an error if the request failed
    card_data = response.json()
    with open(CARDINFO_FILENAME, "w", encoding="utf-8") as f:
        json.dump(card_data, f, ensure_ascii=False, indent=4)
else:
    print("Loading card data from local file...")
    with open(CARDINFO_FILENAME, "r", encoding="utf-8") as f:
        card_data = json.load(f)

# Build a lookup dictionary: key = card id (as string), value = card info dict
card_info = {}
for card in card_data.get("data", []):
    card_id_str = str(card["id"])
    card_info[card_id_str] = card

# ----- Step 2: Process all YDK files and build statistics and co-occurrence counts -----
# Change this path to where your YDK files are located.
YDK_FOLDER = r"C:\Users\morit\Documents\ydk_download"
ydk_files = [f for f in os.listdir(YDK_FOLDER) if f.endswith(".ydk")]

# Dictionaries to store per-card usage and co-occurrence counts.
card_stats = {}  # Format: { card_id: {"total": count, "main": count, "extra": count, "side": count} }
edge_counter = Counter()  # For pairs of card IDs (tuple sorted) --> co-occurrence count

print("Processing YDK files...")
for filename in ydk_files:
    filepath = os.path.join(YDK_FOLDER, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Prepare structure for the three sections.
    deck = {"main": [], "extra": [], "side": []}
    current_section = None

    # Parse the file line by line.
    for line in lines:
        line = line.strip()
        # Detect section headers (they may start with '#' or '!')
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
        # If the line is a digit (i.e. a card ID) and we are inside a section…
        elif line and line.isdigit() and current_section:
            deck[current_section].append(line)

    # Update per-card statistics.
    for section, card_list in deck.items():
        for card in card_list:
            if card not in card_stats:
                card_stats[card] = {"total": 0, "main": 0, "extra": 0, "side": 0}
            card_stats[card]["total"] += 1
            card_stats[card][section] += 1

    # For co-occurrence, use the unique set of cards in the deck (ignoring duplicates).
    unique_cards = set(deck["main"] + deck["extra"] + deck["side"])
    # Update co-occurrence counts for every unique pair in this deck.
    for card_a, card_b in itertools.combinations(sorted(unique_cards), 2):
        edge_counter[(card_a, card_b)] += 1

print("Finished processing decks.")

# Count cards that never appear in any deck.
unused_cards = [cid for cid in card_info.keys() if cid not in card_stats]
print(f"Total cards in API: {len(card_info)}")
print(f"Cards that never appeared in a deck: {len(unused_cards)}")

# ----- Step 3: Build an interactive network graph with PyVis -----
# You can adjust the edge_threshold to filter out low-frequency co-occurrences.
EDGE_THRESHOLD = 30

# Create a PyVis Network. The 'notebook=False' option will open it in your default browser.
net = Network(height="800px", width="100%", bgcolor="#222222", font_color="white", notebook=False)
# Enable built-in physics configuration UI.
net.show_buttons(filter_=['physics'])

# Add nodes for each card that appears in at least one deck.
for card_id, stats in card_stats.items():
    # Use the card's name from the API data if available.
    card = card_info.get(card_id, {})
    name = card.get("name", card_id)
    # Create an HTML tooltip (title) showing the statistics.
    title = (
        f"<b>{name}</b><br>"
        f"Total appearances: {stats['total']}<br>"
        f"Main: {stats['main']} &nbsp;&nbsp; Extra: {stats['extra']} &nbsp;&nbsp; Side: {stats['side']}"
    )
    net.add_node(card_id, label=name, title=title)

# Add edges between cards that meet the threshold.
print("Adding edges (this may take a moment)...")
for (card_a, card_b), weight in edge_counter.items():
    if weight >= EDGE_THRESHOLD:
        # The edge title (tooltip) shows the co-occurrence count.
        net.add_edge(card_a, card_b, value=weight, title=f"Co-occurrence in decks: {weight}")

# ----- Step 4: Save and show the network -----
output_file = "yugioh_cluster.html"
net.show(output_file, notebook=False)
print(f"Interactive network saved to {output_file}. It will open in your browser.")
