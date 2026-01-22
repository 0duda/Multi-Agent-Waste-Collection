import pygame
import sys
import tkinter as tk
from tkinter import simpledialog
from environment import Environment, load_environment_from_json
import asyncio
import os
import json

# Initialize Pygame only once
pygame.init()

# Colors
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
BLACK = (0, 0, 0)
BLUE = (0, 0, 255)
GREY = (128, 128, 128)
BROWN = (139, 69, 19)  # Brown for organic bins
DARK_GREEN = (0, 100, 0)  # Dark green for recyclable bins
YELLOW = (255, 255, 0)
ORANGE = (255, 165, 0)

# Global variables to be defined later
CELL_SIZE = 50
WIDTH, HEIGHT = 0, 0
screen = None
env = None
scroll_offset = 0
MAX_SCROLL = 0
system_start_time = None  # ADDED: Timer variable

mode = None

# Pre-defined layouts
layout_2 = [[0,0,0,0,5,0,0,0,0,0,0],
            [5,5,5,0,5,0,5,0,5,5,5],
            [0,5,0,0,5,0,5,0,0,0,0],
            [0,5,0,0,0,0,0,0,0,5,0],
            [0,0,0,0,5,5,5,0,0,5,0],
            [0,5,0,0,5,0,0,0,0,5,0],
            [0,5,0,0,5,5,5,0,0,5,0],
            [0,0,0,0,0,0,0,0,0,0,0],
            [0,5,0,5,0,0,0,5,5,5,0],
            [5,5,0,5,0,5,5,5,0,5,0],
            [0,0,0,5,0,0,0,0,0,5,0]]

layout_1 = [
      [0,0,0,5,5,0,0,0,5,0,0],
      [0,5,0,0,5,0,5,0,5,0,0],
      [0,5,5,0,0,0,5,0,0,0,5],
      [0,0,0,0,5,0,0,0,0,0,0],
      [5,5,0,5,0,0,5,5,0,5,0],
      [0,0,0,0,0,0,0,0,0,0,0],
      [0,5,0,0,5,5,5,0,0,0,0],
      [0,0,0,5,0,0,5,0,5,0,5],
      [5,0,0,0,0,0,0,0,0,0,0],
      [0,5,0,5,5,0,0,5,0,0,0],
      [0,0,0,0,0,0,5,0,0,0,0]
    ]

# Load truck images (now as a function)
def load_truck_images():
    """
    Load and process truck images for the simulation.

    Returns:
        tuple: A tuple containing 4 Pygame surfaces:
               (organic_normal, recyclable_normal, organic_broken, recyclable_broken).
    """
    try:
        organic_truck_image = pygame.image.load("Images/organic_truck.png")
        organic_truck_image = pygame.transform.scale(organic_truck_image, (CELL_SIZE - 5, CELL_SIZE - 5))
        
        recyclable_truck_image = pygame.image.load("Images/recyclable_truck.png")
        recyclable_truck_image = pygame.transform.scale(recyclable_truck_image, (CELL_SIZE - 5, CELL_SIZE - 5))
        
        def apply_red_filter(image):
            """
            Apply a transparent red overlay to the image to simulate a 'broken' state.
            
            Args:
                image (pygame.Surface): The original truck image.

            Returns:
                pygame.Surface: The red-tinted image.
            """
            red_surface = pygame.Surface(image.get_size(), pygame.SRCALPHA)
            red_surface.fill((255, 0, 0, 128))
            red_surface.blit(image, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            return red_surface
        
        organic_truck_broken = apply_red_filter(organic_truck_image)
        recyclable_truck_broken = apply_red_filter(recyclable_truck_image)
        
        return organic_truck_image, recyclable_truck_image, organic_truck_broken, recyclable_truck_broken
        
    except pygame.error as e:
        print(f"Error loading truck images: {e}")
        print("Using colored rectangles instead")
        # Fallback: create colored surfaces
        organic_truck_image = pygame.Surface((CELL_SIZE - 5, CELL_SIZE - 5))
        organic_truck_image.fill(BROWN)
        recyclable_truck_image = pygame.Surface((CELL_SIZE - 5, CELL_SIZE - 5))
        recyclable_truck_image.fill(DARK_GREEN)
        organic_truck_broken = apply_red_filter(organic_truck_image)
        recyclable_truck_broken = apply_red_filter(recyclable_truck_image)
        
        return organic_truck_image, recyclable_truck_image, organic_truck_broken, recyclable_truck_broken

def initialize_bin_names_from_environment(env):
    """
    Generate display names for bins based on the loaded environment.

    Args:
        env (Environment): The simulation environment object.

    Returns:
        dict: A dictionary mapping (row, col) coordinates to bin names (e.g., "1(O)").
    """
    bin_names = {}
    for i, (pos, bin_agent) in enumerate(env.bins.items()):
        # Convert environment position to grid coordinates
        # In environment: position is stored as (row, col) = (y, x)
        # In bin_names: we need (row, col) for drawing
        row, col = bin_agent.position
        type_char = 'O' if bin_agent.waste_type == 'organic' else 'R'
        bin_names[(row, col)] = f"{i+1}({type_char})"
    return bin_names

def draw_environment(grid, trucks, traffic_edges, bin_names, bins, truck_images):
    """
    Render the simulation grid, agents, and elements onto the main screen.

    Args:
        grid (list): The 2D grid matrix.        
        trucks (list): List of TruckAgent objects.      
        traffic_edges (list): List of graph edges affected by traffic.      
        bin_names (dict): Mapping of coordinates to bin labels.         
        bins (dict): Dictionary of bin objects.         
        truck_images (tuple): Tuple containing the preloaded truck images.      
    """
    organic_truck_image, recyclable_truck_image, organic_truck_broken, recyclable_truck_broken = truck_images
    
    for row in range(len(grid)):
        for col in range(len(grid[0])):
            color = WHITE
            bin_obj = env.get_bin_at_position((row, col))
            if bin_obj:
                color = GREEN if bin_obj.waste_type == "recyclable" else BROWN

            elif grid[row][col] == 2:   # Central
                color = BLUE
            elif grid[row][col] == -1:  # Obstacle
                color = BLACK
            elif grid[row][col] == 9:   # Roadblock
                color = ORANGE  
            elif grid[row][col] == 5:
                color = GREY

            pygame.draw.rect(
                screen,
                color,
                pygame.Rect(col * CELL_SIZE, row * CELL_SIZE, CELL_SIZE, CELL_SIZE),
            )

            pygame.draw.rect(
                screen,
                BLACK,
                pygame.Rect(col * CELL_SIZE, row * CELL_SIZE, CELL_SIZE, CELL_SIZE),
                1,
            )

            # Check if there is a name associated with the square
            if (row, col) in bin_names:
                name = bin_names[(row, col)]
                text_surface = pygame.font.Font(None, 24).render(name, True, (0, 0, 0))
                text_rect = text_surface.get_rect(center=(col * CELL_SIZE + CELL_SIZE // 2, row * CELL_SIZE + CELL_SIZE // 2))
                screen.blit(text_surface, text_rect)

    # Draw traffic edges
    if traffic_edges:
        for (pos1, pos2) in traffic_edges:
            x1 = pos1[1] * CELL_SIZE + CELL_SIZE // 2
            y1 = pos1[0] * CELL_SIZE + CELL_SIZE // 2
            x2 = pos2[1] * CELL_SIZE + CELL_SIZE // 2
            y2 = pos2[0] * CELL_SIZE + CELL_SIZE // 2
            pygame.draw.line(screen, RED, (x1, y1), (x2, y2), 5)  

    # Draws the trucks
    for truck in trucks:
        x, y = truck.position

        # Choose the correct truck image based on type
        if truck.truck_type == "organic":
            truck_img = organic_truck_broken if truck.is_broken else organic_truck_image
        else:  # recyclable
            truck_img = recyclable_truck_broken if truck.is_broken else recyclable_truck_image

        image_x = y * CELL_SIZE + (CELL_SIZE - truck_img.get_width()) // 2
        image_y = x * CELL_SIZE + (CELL_SIZE - truck_img.get_height()) // 2
        screen.blit(truck_img, (image_x, image_y))

def draw_metrics_surface(trucks, bins):
    """
    Create and render the side panel with statistics and controls (timer, waste level, fuel, capacity and instructions).

    Args:
        trucks (dict): Dictionary containing truck status data.         
        bins (dict): Dictionary containing bin status data.

    Returns:
        pygame.Surface: The rendered subsurface ready to be blitted.
    """
    global MAX_SCROLL, system_start_time
    surface_width = 600
    surface_height = 2000  # Start large; we'll adjust later
    metrics_surface = pygame.Surface((surface_width, surface_height))
    metrics_surface.fill(BLACK)

    metrics_y = 20
    
    #Timer display at the top
    if system_start_time is not None:
        elapsed_time = env.timer() - system_start_time
        time_text = pygame.font.Font(None, 36).render(f"Time: {elapsed_time:.1f}s", True, WHITE)
        metrics_surface.blit(time_text, (20, metrics_y))
        metrics_y += 40

    # BIN STATUS 
    title = pygame.font.Font(None, 36).render("Bins", True, WHITE)  
    metrics_surface.blit(title, (20, metrics_y))
    metrics_y += 40

    organic_bins = {k: v for k, v in bins.items() if "organic" in k.lower()}
    recyclable_bins = {k: v for k, v in bins.items() if "recyclable" in k.lower()}

    if organic_bins:
        type_title = pygame.font.Font(None, 32).render("Organic Bins:", True, BROWN)
        metrics_surface.blit(type_title, (20, metrics_y))
        metrics_y += 30
        for bin_id, info in organic_bins.items():
            color = GREEN if info[0] < 0.4*info[1] else YELLOW if info[0] < 0.7*info[1] else RED
            text = pygame.font.Font(None, 28).render(f"{bin_id}: {info[0]}/{info[1]}", True, color)
            metrics_surface.blit(text, (40, metrics_y))
            metrics_y += 30

    if recyclable_bins:
        type_title = pygame.font.Font(None, 32).render("Recyclable Bins:", True, DARK_GREEN)
        metrics_surface.blit(type_title, (20, metrics_y))
        metrics_y += 30
        for bin_id, info in recyclable_bins.items():
            color = GREEN if info[0] < 0.4*info[1] else YELLOW if info[0] < 0.7*info[1] else RED
            text = pygame.font.Font(None, 28).render(f"{bin_id}: {info[0]}/{info[1]}", True, color)
            metrics_surface.blit(text, (40, metrics_y))
            metrics_y += 30

    # TRUCK STATUS
    metrics_y += 20
    title = pygame.font.Font(None, 36).render("Trucks", True, WHITE) 
    metrics_surface.blit(title, (20, metrics_y))
    metrics_y += 40

    organic_trucks = {k: v for k, v in trucks.items() if "organic" in k.lower()}
    recyclable_trucks = {k: v for k, v in trucks.items() if "recyclable" in k.lower()}

    if organic_trucks:
        type_title = pygame.font.Font(None, 32).render("Organic Trucks:", True, BROWN)
        metrics_surface.blit(type_title, (20, metrics_y))
        metrics_y += 30
        for truck_id, info in organic_trucks.items():
            text = pygame.font.Font(None, 28).render(
                f"{truck_id}: Cap {info[0]}/{info[1]}, Fuel {info[2]}/{info[3]}", True, WHITE)
            metrics_surface.blit(text, (40, metrics_y))
            metrics_y += 30

    if recyclable_trucks:
        type_title = pygame.font.Font(None, 32).render("Recyclable Trucks:", True, DARK_GREEN)
        metrics_surface.blit(type_title, (20, metrics_y))
        metrics_y += 30
        for truck_id, info in recyclable_trucks.items():
            text = pygame.font.Font(None, 28).render(
                f"{truck_id}: Cap {info[0]}/{info[1]}, Fuel {info[2]}/{info[3]}", True, WHITE)
            metrics_surface.blit(text, (40, metrics_y))
            metrics_y += 30

    # CONTROLS / GUIDELINES 
    metrics_y += 40
    title = pygame.font.Font(None, 36).render("Controls", True, YELLOW)
    metrics_surface.blit(title, (20, metrics_y))
    metrics_y += 40

    controls = [
        "B + Left Click - Organic Bin",
        "N + Left Click - Recyclable Bin",
        "T + Left Click - Organic Truck",
        "Y + Left Click - Recyclable Truck",
        "R + Left/Right Click - Add/Remove Roadblock",
        "S - Start System",
        "1-5 - Define Traffic level",
        "0 - Reset Traffic",
        "Close Window - Save data",
        "Scroll down with Mouse Wheel"
    ]

    for control in controls:
        text = pygame.font.Font(None, 24).render(control, True, WHITE)
        metrics_surface.blit(text, (40, metrics_y))
        metrics_y += 25

    # Force minimum height to allow scrolling even with little content
    min_height = 2000  
    final_height = max(metrics_y + 100, min_height)

    metrics_surface = metrics_surface.subsurface((0, 0, surface_width, final_height))
    MAX_SCROLL = final_height - HEIGHT

    return metrics_surface

def write_file(trucks, bins):
    """
    Generate a comprehensive performance report and save it to a text file.

    Args:
        trucks (list): List of truck objects.       
        bins (dict): Dictionary of bin objects.
    """
    filename = "metrics_results.txt"
    with open(filename, "w") as file:
        file.write("Ambiente com constante waste accumulation (5s) e possibilidade de breaks.\n\n")

        # Truck Data 
        total_fuel = 0
        total_distance = 0
        total_waste = 0
        total_collabs = 0

        for truck in trucks:
            truck_data = (
                f"TRUCK: {truck.jid} [{truck.truck_type}]\n"
                f"  - Total waste collected: {truck.collected_waste}\n"
                f"  - Total fuel spent: {truck.total_fuel}\n"
                f"  - Total distance travelled: {truck.total_distance}\n"
                f"  - Total number of collabs: {truck.collab}\n\n"
            )
            file.write(truck_data)

            total_fuel += truck.total_fuel
            total_distance += truck.total_distance
            total_waste += truck.collected_waste
            total_collabs += truck.collab

        # Bin Data 
        total_bins = len(bins)
        collected_before_overflow = 0

        # Metrics for performance analysis
        successful_cfp_collections = 0
        total_autonomous_collections = 0
        total_collection_time = 0
        all_collection_times = []  # only for CFP
        bins_with_any_collection = 0
        total_collections_all_types = 0  # TOTAL of all collections

        # Statistics by waste type
        organic_waste_collected = 0
        recyclable_waste_collected = 0
        total_organic_bins = 0
        total_recyclable_bins = 0

        for bin in bins.values():
            overflow_count = len(bin.overflow_times)

            # USE SPECIFIC COUNTERS
            cfp_collections = getattr(bin, 'cfp_collections', 0)
            autonomous_collections = getattr(bin, 'autonomous_collections', 0)
            total_collections = cfp_collections + autonomous_collections
            
            # Count bins by type
            if bin.waste_type == "organic":
                total_organic_bins += 1
            else:
                total_recyclable_bins += 1
            
            # Count if collected before overflow (at least one collection)
            if total_collections > 0 and overflow_count == 0:
                collected_before_overflow += 1
            
            # Calculate collection time statistics (CFP only)
            if len(bin.collection_time) > 0:
                successful_cfp_collections += cfp_collections
                total_collection_time += sum(bin.collection_time)
                all_collection_times.extend(bin.collection_time)
            
            # Estimate collected waste (based on total number of collections)
            waste_per_collection = bin.max_capacity * 0.5  # Estimate: each collection removes ~50%
                
            total_estimated_waste = total_collections * waste_per_collection
            total_collections_all_types += total_collections
            total_autonomous_collections += autonomous_collections
            
            if bin.waste_type == "organic":
                organic_waste_collected += total_estimated_waste
            else:
                recyclable_waste_collected += total_estimated_waste
            
            file.write(f"BIN {bin.jid} [{bin.waste_type}]:\n")
            
            file.write(f"  - Total collections: {total_collections}\n")
            file.write(f"  - CFP collections: {cfp_collections}\n")
            file.write(f"  - Autonomous collections: {autonomous_collections}\n")
            file.write(f"  - CFP collection times: {[f'{t:.2f}s' for t in bin.collection_time]}\n")
            file.write(f"  - Overflow count: {overflow_count}\n")
            
            if total_collections > 0:
                bins_with_any_collection += 1
                file.write(f"  - Collection rate: {total_collections} collections\n")
            else:
                file.write("  - No collections recorded\n")
            
            if len(bin.collection_time) > 0:
                avg_time = sum(bin.collection_time) / len(bin.collection_time)
                file.write(f"  - Average CFP response time: {avg_time:.2f}s\n\n")
            else:
                file.write("  - No CFP collections\n\n")

        # PERFORMANCE METRICS
        file.write("\n" + "="*50 + "\n")
        file.write("SYSTEM PERFORMANCE METRICS\n")
        file.write("="*50 + "\n\n")

        # 1. System Efficiency
        file.write("SYSTEM EFFICIENCY:\n")
        file.write("-" * 20 + "\n")
        
        overflow_efficiency = (collected_before_overflow / total_bins * 100) if total_bins > 0 else 0
        file.write(f"Bins collected before overflow: {collected_before_overflow}/{total_bins} ({overflow_efficiency:.1f}%)\n")
        
        collection_rate = (bins_with_any_collection / total_bins * 100) if total_bins > 0 else 0
        file.write(f"Bins with at least one collection: {bins_with_any_collection}/{total_bins} ({collection_rate:.1f}%)\n")
        
        file.write(f"Total collections (all types): {total_collections_all_types}\n")
        file.write(f"CFP collections: {successful_cfp_collections}\n")
        file.write(f"Autonomous collections: {total_autonomous_collections}\n")

        # 2. Response Times (CFP only)
        file.write("\nRESPONSE TIMES (CFP only):\n")
        file.write("-" * 25 + "\n")
        
        if successful_cfp_collections > 0:
            avg_response_time = total_collection_time / successful_cfp_collections
            file.write(f"Average CFP response time: {avg_response_time:.2f}s\n")
            file.write(f"Total CFP collections: {successful_cfp_collections}\n")
            
            if all_collection_times:
                min_time = min(all_collection_times)
                max_time = max(all_collection_times)
                file.write(f"Quickest CFP collection: {min_time:.2f}s\n")
                file.write(f"Slowest CFP collection: {max_time:.2f}s\n")
        else:
            file.write("No CFP collections recorded\n")

        # 3. Recycling Statistics
        file.write("\nRECYCLING STATISTICS:\n")
        file.write("-" * 20 + "\n")
        
        total_waste_collected = organic_waste_collected + recyclable_waste_collected
        if total_waste_collected > 0:
            recycling_rate = (recyclable_waste_collected / total_waste_collected * 100)
            file.write(f"Estimated recycling rate: {recycling_rate:.1f}%\n")
        file.write(f"Organic bins: {total_organic_bins}\n")
        file.write(f"Recyclable bins: {total_recyclable_bins}\n")
        file.write(f"Estimated organic waste collected: {organic_waste_collected:.0f} units\n")
        file.write(f"Estimated recyclable waste collected: {recyclable_waste_collected:.0f} units\n")

        # 4. Truck Efficiency
        file.write("\nTRUCK EFFICIENCY:\n")
        file.write("-" * 15 + "\n")
        
        fuel_efficiency = (total_waste / total_fuel) if total_fuel > 0 else 0
        distance_efficiency = (total_waste / total_distance) if total_distance > 0 else 0
        
        file.write(f"Waste collected per fuel unit: {fuel_efficiency:.2f}\n")
        file.write(f"Waste collected per distance unit: {distance_efficiency:.2f}\n")
        file.write(f"Total fuel consumed: {total_fuel}\n")
        file.write(f"Total distance traveled: {total_distance}\n")

        # 5. Collaboration & Resilience
        file.write("\nCOLLABORATION & RESILIENCE:\n")
        file.write("-" * 25 + "\n")
        
        broke_trucks = sum(1 for truck in trucks if hasattr(truck, 'is_broken') and truck.is_broken)
        responsiveness = total_collabs / max(1, broke_trucks) if broke_trucks > 0 else total_collabs
        file.write(f"Collaborations per breakdown: {responsiveness:.2f}\n")
        
        collab_rate = total_collabs / max(1, len(trucks))
        file.write(f"Average collaborations per truck: {collab_rate:.2f}\n")
        file.write(f"Total collaborations: {total_collabs}\n")
        file.write(f"Trucks that experienced breakdowns: {broke_trucks}\n")

        # 6. General Summary
        file.write("\nOVERALL SUMMARY:\n")
        file.write("-" * 15 + "\n")
        if system_start_time is not None:
            real_time = env.timer() - system_start_time
            file.write(f"Total simulation time: {real_time:.2f}s\n")
        else:
            # Fallback: use max collection time if available, else 0
            if all_collection_times:
                file.write(f"Total simulation time: {max(all_collection_times):.0f}s\n")
            else:
                file.write("Total simulation time: 0s (system not started or no collections)\n")
        file.write(f"Total waste collected: {total_waste:.0f} units\n")
        file.write(f"Total trucks: {len(trucks)}\n")
        file.write(f"Total bins: {total_bins}\n")

    # SIMULATION REAL TIME 
    if system_start_time is not None:
        real_time = env.timer() - system_start_time
        with open(filename, "a") as file:
            file.write(f"Actual simulation run time: {real_time:.2f}s\n")

    print(f"Os dados foram salvos no arquivo '{filename}' com métricas de performance incluídas.")

async def pygame_loop():
    """Execute the main asynchronous game loop (event processing, drawing calls and asynchronous updates)."""
    global scroll_offset, screen, bin_names, system_start_time
    
    # Load truck images
    truck_images = load_truck_images()
    
    running = True
    pressed_keys = set()
    roadblocks = []
    last_broke_truck_time = None
    bins_status = {}
    truck_status = {}
    
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                pressed_keys.add(event.key)
                
                # System Controls
                if event.key == pygame.K_s:
                    await env.start_system()
                    print("Sistema inicializado")
                    if last_broke_truck_time is None:
                        last_broke_truck_time=env.timer()
                    system_start_time = env.timer()  # Set system start time
                elif event.key == pygame.K_1:
                    await env.set_traffic(level=1)
                    print("Traffic level set to 1")
                elif event.key == pygame.K_2:
                    await env.set_traffic(level=2)
                    print("Traffic level set to 2")
                elif event.key == pygame.K_3:
                    await env.set_traffic(level=3)
                    print("Traffic level set to 3")
                elif event.key == pygame.K_4:
                    await env.set_traffic(level=4)
                    print("Traffic level set to 4")
                elif event.key == pygame.K_5:
                    await env.set_traffic(level=5)
                    print("Traffic level set to 5")
                elif event.key == pygame.K_0:
                    await env.set_traffic(level=0)
                    print("Traffic reset to level 0")
            elif event.type == pygame.KEYUP:
                pressed_keys.discard(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                x, y = pygame.mouse.get_pos()
                grid_x, grid_y = y // CELL_SIZE, x // CELL_SIZE
                
                # Check if click is in the metrics area for scrolling
                if x > WIDTH:
                    if event.button == 4:  # Mouse wheel up
                        scroll_offset = max(0, scroll_offset - 30)
                    elif event.button == 5:  # Mouse wheel down
                        scroll_offset = min(MAX_SCROLL, scroll_offset + 30)
                else:
                    # Existing click handling for map area
                    if event.button == 1:  # Left click
                        if pygame.K_b in pressed_keys:  # Organic Bin
                            await env.add_bin((grid_y, grid_x), "organic")
                            bin_names[(grid_x, grid_y)] = f"{len(bin_names)+1}(O)"
                        elif pygame.K_n in pressed_keys:  # Recyclable Bin
                            await env.add_bin((grid_y, grid_x), "recyclable")
                            bin_names[(grid_x, grid_y)] = f"{len(bin_names)+1}(R)"
                        elif pygame.K_t in pressed_keys:  # Organic Truck
                            await env.add_truck((grid_y, grid_x), "organic")
                        elif pygame.K_y in pressed_keys:  # Recyclable Truck
                            await env.add_truck((grid_y, grid_x), "recyclable")
                        elif pygame.K_r in pressed_keys:  # Add Roadblock
                            await env.add_roadBlock((grid_y, grid_x))
                            roadblocks.append((grid_y, grid_x))
                    elif event.button == 3:  # Right click
                        if pygame.K_r in pressed_keys:  # Remove Roadblock
                            if (grid_y, grid_x) in roadblocks:
                                await env.remove_roadBlock((grid_y, grid_x))
                                roadblocks.remove((grid_y, grid_x))
                            else:
                                print("Não existe um roadblock nessa posição")

        if last_broke_truck_time is not None:
            last_broke_truck_time = env.break_truck(last_broke_truck_time)

        grid, trucks, bins, traffic_edges = env.update_display()

        bins_status = {}
        for bin in bins.values():
            bins_status[bin.name] = [bin.current_waste, bin.max_capacity]

        truck_status = {}
        for truck in trucks:
            truck_status[truck.name] = [truck.load, truck.max_load, truck.fuel, truck.max_fuel]

        # Updates the screen
        screen.fill(WHITE)
        draw_environment(grid, trucks, traffic_edges, bin_names, bins, truck_images)
        metrics_surface = draw_metrics_surface(truck_status, bins_status)

        # Create a viewable window of the right-side menu
        visible_area = pygame.Rect(0, scroll_offset, 600, HEIGHT)
        screen.blit(metrics_surface, (WIDTH, 0), area=visible_area)

        
        # Draw scroll indicator if needed
        if MAX_SCROLL > 0:
            scroll_indicator = f"Scroll: {scroll_offset}/{MAX_SCROLL} (Mouse Wheel)"
            indicator_text = pygame.font.Font(None, 20).render(scroll_indicator, True, BLACK)
            screen.blit(indicator_text, (WIDTH + 20, HEIGHT - 25))
        
        pygame.display.flip()

        await asyncio.sleep(0.03)
    
    pygame.quit()
    
    # Stop all agents before writing the file
    print("A parar todos os agentes...")
    for truck in env.trucks:
        await truck.stop()
    for bin in env.bins.values():
        await bin.stop()
    
    # Short pause to ensure all agents have stopped
    await asyncio.sleep(2)
    
    grid, trucks, bins, traffic_edges = env.update_display()
    write_file(trucks, bins)
    
    # Terminate the process correctly
    import sys
    sys.exit(0)

async def main():
    """Main entry point. Handles configuration and startup."""
    global env, rows, cols, mode, screen, WIDTH, HEIGHT, bin_names

    # Initialize bin_names as empty dictionary
    bin_names = {}

    # Mode selection
    if mode is None:
        root = tk.Tk()
        root.withdraw()
        mode = simpledialog.askstring("Mode Selection", "Choose mode: 'layout' or 'manual'", parent=root)
        root.destroy()

    if mode == "layout":
        root = tk.Tk()
        root.withdraw()
        layout_file = simpledialog.askstring("Layout Selection", "Enter layout filename (e.g., layout1.json)", parent=root)
        root.destroy()
        if layout_file and os.path.exists(layout_file):
            try:
                env = await load_environment_from_json(layout_file)
                print("Environment loaded successfully from JSON")
                
                # Use the environment's actual dimensions
                rows, cols = env.height, env.width
                print(f"Environment size: {rows}x{cols}")

                # NEW: Initialize bin names from loaded environment
                bin_names = initialize_bin_names_from_environment(env)
                print(f"Initialized {len(bin_names)} bin names")

            except Exception as e:
                print(f"Error loading environment: {e}")
                print("Switching to manual mode.")
                mode = "manual"
        else:
            print("File not found. Switching to manual mode.")
            mode = "manual"

    if mode == "manual":
        root = tk.Tk()
        root.withdraw()
        layout_choice = simpledialog.askstring("Manual Layout Selection", "Choose layout: '1' or '2'", parent=root)
        root.destroy()
        layout = layout_2 if layout_choice == "2" else layout_1
        rows, cols = len(layout), len(layout[0])
        env = Environment(cols, rows, layout)
        print(f"Manual mode: Using layout_{layout_choice if layout_choice in ['1','2'] else '1'}")

    # Initialize Pygame display AFTER we know the dimensions
    WIDTH, HEIGHT = cols * CELL_SIZE, rows * CELL_SIZE
    screen = pygame.display.set_mode((WIDTH + 600, HEIGHT))
    pygame.display.set_caption("Multi-Agent Autonomous Waste Collection System")
    
    print(f"Pygame window created: {WIDTH}x{HEIGHT}")
    print("Ready! Press 'S' to start the system.")

    # Run Pygame loop
    await pygame_loop()

if __name__ == "__main__":
    # Ensure the asyncio loop terminates completely
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        print("Programa terminado completamente")