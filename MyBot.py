#!/usr/bin/env python3
# Python 3.6

# Import the Halite SDK, which will let you interact with the game.
import hlt

# This library contains constant values.
from hlt import constants

# This library contains direction metadata to better interface with the game.
from hlt.positionals import Direction

# This library allows you to generate random numbers.
import random

# Logging allows you to save messages for yourself. This is required because the regular STDOUT
#   (print statements) are reserved for the engine-bot communication.
import logging

""" <<<Game Begin>>> """

# This game object contains the initial game state.
game = hlt.Game()

# At this point "game" variable is populated with initial map data.
# This is a good place to do computationally expensive start-up pre-processing.
# As soon as you call "ready" function below, the 2 second per turn timer will start.
game.ready("GoldBot")

# Now that your bot is initialized, save a message to yourself in the log file with some important information.
#   Here, you log here your id, which you can always fetch from the game object by using my_id.
logging.info("Successfully created bot! My Player ID is {}.".format(game.my_id))
logging.info("MAX TURNS = {}".format(constants.MAX_TURNS))

""" <<<Game Loop>>> """

ship_states = {}
dropoffs_count = 0
alarm = False

while True:
    # This loop handles each turn of the game. The game object changes every turn, and you refresh that state by
    #   running update_frame().
    game.update_frame()
    # You extract player metadata and the updated map metadata here for convenience.
    me = game.me
    game_map = game.game_map

    # A command queue holds all the commands you will run this turn. You build this list up and submit it at the
    #   end of the turn.
    command_queue = []

    # Store the commnands for each ship in a dictionary and a flag if it's arranged to swap. Then transfer the commands to above queue.
    # {ship_id: (command, swap_flag) }
    commands_dict = {}

    direction_options = Direction.get_all_cardinals()
    dropoff_created = False

    for ship in me.get_ships():

        if ship.id in commands_dict:
            continue

        # ships just spawned should be collecting
        if ship.id not in ship_states:
            ship_states[ship.id] = "collecting"

        if constants.MAX_TURNS - game.turn_number <= 20:
            alarm = True
            ship_states[ship.id] = "depositing"

        # Create a dropoff if ship is far away
        if dropoffs_count < game_map.width//12 and not dropoff_created and me.halite_amount > constants.DROPOFF_COST and \
                ship_states[ship.id] == "depositing" and game.turn_number < constants.MAX_TURNS * 0.8:
            nearest = game_map.nearest_base(ship, me)
            if nearest[1] > game_map.width * 0.4:
                commands_dict[ship.id] = (ship.make_dropoff(), True)
                dropoff_created = True
                dropoffs_count += 1
                continue

        position_options = ship.position.get_surrounding_cardinals()

        # movement direction mapped to actual map coordinates
        position_dict = {}

        # movement direction mapped to halite amount
        halite_dict = {}

        # Populate dictionaries
        # Because the directional choice of each ship depends on the position with the most halite, don't
        #   populate halite_dict with a position if it's a conflicting coordinate (based on position_choices)
        for n, direction in enumerate(direction_options):
            position_dict[direction] = position_options[n]

        for direction in position_dict:
            position = position_dict[direction]
            if not game_map[position].is_occupied:
                halite_amount = game_map[position].halite_amount
                halite_dict[direction] = halite_amount

        # Navigate back to shipyard if the ship is in depositing phase
        if ship_states[ship.id] == "depositing":
 
            # deposited halite, begin collecting again
            if ship.halite_amount == 0 and not alarm:
                ship_states[ship.id] = "collecting"
            else:
                # find the nearest base to deposit halite
                nearest_base = game_map.nearest_base(ship, me)[0]
                directional_choice = game_map.naive_navigate(ship, nearest_base)

                if directional_choice == Direction.Still:
                    unsafe_moves = game_map.get_unsafe_moves(ship.position, nearest_base)

                    for direction in unsafe_moves:                  
                        target_pos = ship.position.directional_offset(direction)
                        blocking_ship = game_map[target_pos].ship

                        # in case of last remaining turns alarm collide all ships in base
                        if alarm and game_map[target_pos].has_structure:
                            directional_choice = direction
                            break
                         
                        if blocking_ship.owner != me.id:
                            # if enemy blocks my base, collide ships
                            if game_map.calculate_distance(blocking_ship.position, nearest_base) <= 1:
                                directional_choice = direction
                            break

                        # if can't move closer to shipyard, swap with a blocking ship if possible
                        if  game_map[blocking_ship.position] != game_map[target_pos] or \
                            blocking_ship.halite_amount < game_map[blocking_ship.position].halite_amount * 0.1:
                            continue

                        state = ship_states[blocking_ship.id] if blocking_ship.id in ship_states else "collecting"
                        flag = commands_dict[blocking_ship.id][1] if blocking_ship.id in commands_dict else False
                        if state != "depositing" and flag == False:
                            directional_choice = direction
                            commands_dict[blocking_ship.id] = (blocking_ship.move(Direction.invert(directional_choice)), True)
                            break
                
                commands_dict[ship.id] = (ship.move(directional_choice), False)

        # Move towards the most halite if the ship is in collecting phase
        if ship_states[ship.id] == "collecting":
            hlt_left = game_map[ship.position].halite_amount

            if not halite_dict or ship.halite_amount < hlt_left * 0.1 or hlt_left > 80:
                directional_choice = Direction.Still
            else:
                dir_max = max(halite_dict, key = lambda v: halite_dict[v])
                directional_choice = Direction.Still if hlt_left > halite_dict[dir_max]//2 else dir_max
            
            target_pos = ship.position.directional_offset(directional_choice)
            commands_dict[ship.id] = (ship.move(game_map.naive_navigate(ship, target_pos)), False)

            if ship.halite_amount > constants.MAX_HALITE * 0.9:
                ship_states[ship.id] = "depositing"

    # If the game is in the first 200 turns and you have enough halite, spawn a ship.
    # Don't spawn a ship if you currently have a ship at port, though - the ships will collide.
    if game.turn_number <= constants.MAX_TURNS * 0.5 and me.halite_amount >= constants.SHIP_COST and not game_map[me.shipyard].is_occupied:
        command_queue.append(me.shipyard.spawn())

    for cmd in commands_dict.values():
        command_queue.append(cmd[0])

    # Send your moves back to the game environment, ending this turn.
    game.end_turn(command_queue)