                                                                               

NAMES = (
    ('Evan North', 'Luca Vale', 'Noah Reed', 'Milan West', 'Theo Marsh',
     'Leon Ash', 'Niko Stone', 'Alex Birch', 'Finn Lake', 'Max Rowan', 'Owen Fox'),
    ('Adam Frost', 'Emil Brook', 'Ruben Hale', 'Tomas Wren', 'Leo Pine',
     'Dan Rivers', 'Erik Dale', 'Ivan Field', 'Felix Wood', 'Sam Arden', 'Ben Oaks'))


def player_name(team, number):
    return NAMES[team][number-1]


def named_metadata(metadata):
    for team in metadata['teams']:
        for player in team['lineup']:
            player['name'] = player_name(team['id'], player['number'])
    metadata['identities'] = 'fictional synthetic roster'
    return metadata
