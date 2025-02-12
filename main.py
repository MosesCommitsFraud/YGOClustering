import os
import json
import requests
import glob
import itertools
import concurrent.futures
import networkx as nx
from collections import Counter, defaultdict
from pyvis.network import Network
from tqdm import tqdm  # pip install tqdm

# Path to cache card info locally and the API URL.
CARD_INFO_FILE = "cards.json"
CARD_INFO_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"

# Path to your YDK files (adjust as needed)
YDK_DIRECTORY = r"C:\Users\morit\Documents\YGO\ydk_download"


def fetch_card_info():
    if os.path.exists(CARD_INFO_FILE):
        print("Loading card info from local cache...")
        with open(CARD_INFO_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        print("Downloading card info from API...")
        response = requests.get(CARD_INFO_URL)
        response.raise_for_status()
        data = response.json()
        with open(CARD_INFO_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)

    card_dict = {}
    for card in data.get("data", []):
        card_dict[str(card["id"])] = card
    return card_dict


def process_deck_file(file_path):
    global_freq = Counter()
    deck_type_freq = {"main": Counter(), "extra": Counter(), "side": Counter()}
    deck_occurrences = Counter()
    cooccurrence = Counter()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return global_freq, deck_type_freq, deck_occurrences, cooccurrence

    current_section = None
    deck_cards = []  # For total count (including duplicates)
    deck_cards_set = set()  # For unique cards in this deck

    for line in lines:
        if line.startswith("#"):
            if line.lower() == "#main":
                current_section = "main"
            elif line.lower() == "#extra":
                current_section = "extra"
            else:
                current_section = None
            continue
        if line.startswith("!"):
            current_section = "side"
            continue
        if not line.isdigit():
            continue
        card_id = line
        global_freq[card_id] += 1
        if current_section in deck_type_freq:
            deck_type_freq[current_section][card_id] += 1
        deck_cards.append(card_id)
        deck_cards_set.add(card_id)

    for card in deck_cards_set:
        deck_occurrences[card] += 1

    for card1, card2 in itertools.combinations(deck_cards_set, 2):
        pair = tuple(sorted((card1, card2)))
        cooccurrence[pair] += 1

    return global_freq, deck_type_freq, deck_occurrences, cooccurrence


def parse_ydk_files_parallel(directory):
    deck_files = glob.glob(os.path.join(directory, "*.ydk"))
    print(f"Found {len(deck_files)} YDK files.")

    total_global = Counter()
    total_deck_type = {"main": Counter(), "extra": Counter(), "side": Counter()}
    total_occurrences = Counter()
    total_cooccurrence = Counter()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(process_deck_file, file): file for file in deck_files}
        # Wrap as_completed with tqdm for progress monitoring
        for future in tqdm(concurrent.futures.as_completed(futures),
                           total=len(futures),
                           desc="Processing decks"):
            global_freq, deck_type_freq, deck_occurrences, cooccurrence = future.result()
            total_global.update(global_freq)
            for section in total_deck_type:
                total_deck_type[section].update(deck_type_freq[section])
            total_occurrences.update(deck_occurrences)
            total_cooccurrence.update(cooccurrence)

    return total_global, total_deck_type, total_occurrences, total_cooccurrence


def build_graph(global_freq, cooccurrence, card_dict, min_edge_weight=3):
    G = nx.Graph()
    for card_id, count in global_freq.items():
        card_name = card_dict.get(card_id, {}).get("name", f"Unknown ({card_id})")
        G.add_node(card_id, label=card_name, title=f"{card_name}<br>Count: {count}", count=count)
    for (card1, card2), weight in cooccurrence.items():
        if weight >= min_edge_weight:
            if card1 in G.nodes and card2 in G.nodes:
                G.add_edge(card1, card2, weight=weight, title=f"Co-occurrence: {weight}")
    return G


def visualize_graph(G, output_filename="card_cluster.html", max_nodes=500):
    """
    Visualizes the graph using pyvis. If the graph has more than `max_nodes`,
    it filters to the top `max_nodes` by node count for faster visualization.
    """
    # If the graph is too large, filter to the top `max_nodes`
    if len(G.nodes) > max_nodes:
        print(f"Graph has {len(G.nodes)} nodes. Filtering to top {max_nodes} nodes by count.")
        # Sort nodes by count (attribute 'count') descending
        top_nodes = sorted(G.nodes(data=True), key=lambda x: x[1].get("count", 0), reverse=True)[:max_nodes]
        node_set = set(node for node, data in top_nodes)
        # Create a subgraph with these nodes
        subG = G.subgraph(node_set).copy()
    else:
        subG = G

    # Initialize pyvis network
    from pyvis.network import Network
    net = Network(height="800px", width="100%", notebook=False, bgcolor="#222222", font_color="white")
    net.barnes_hut()  # Barnes-Hut physics for layout

    # Add nodes to the visualization
    for node, data in subG.nodes(data=True):
        net.add_node(node,
                     label=data.get("label", node),
                     title=data.get("title", ""),
                     value=data.get("count", 1))
    # Add edges
    for source, target, data in subG.edges(data=True):
        net.add_edge(source, target,
                     value=data.get("weight", 1),
                     title=data.get("title", ""))

    # Save and open the visualization
    net.show(output_filename)
    print(f"Graph visualization saved to {output_filename}")


def print_statistics(global_freq, deck_type_freq, deck_occurrences, card_dict):
    print("\n=== Card Appearance Statistics ===")
    for card_id, count in global_freq.most_common():
        card_name = card_dict.get(card_id, {}).get("name", f"Unknown ({card_id})")
        main_count = deck_type_freq["main"].get(card_id, 0)
        extra_count = deck_type_freq["extra"].get(card_id, 0)
        side_count = deck_type_freq["side"].get(card_id, 0)
        print(
            f"{card_name} (ID: {card_id}): Total: {count}, Main: {main_count}, Extra: {extra_count}, Side: {side_count}")

    unused_cards = [card["name"] for cid, card in card_dict.items() if cid not in global_freq]
    print("\n=== Cards Not Used in Any Deck ===")
    for card_name in unused_cards:
        print(card_name)
    print(f"\nTotal unused cards: {len(unused_cards)}")


def main():
    print("=== Loading Card Information ===")
    card_dict = fetch_card_info()

    print("\n=== Parsing YDK Files in Parallel ===")
    global_freq, deck_type_freq, deck_occurrences, cooccurrence = parse_ydk_files_parallel(YDK_DIRECTORY)

    print("\n=== Building Co-occurrence Graph ===")
    G = build_graph(global_freq, cooccurrence, card_dict, min_edge_weight=3)

    print("\n=== Visualizing Graph ===")
    visualize_graph(G)

    print("\n=== Printing Statistics ===")
    print_statistics(global_freq, deck_type_freq, deck_occurrences, card_dict)


if __name__ == "__main__":
    main()
