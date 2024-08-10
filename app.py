from flask import Flask, request, render_template
import numpy as np
import PyPDF2
import requests

app = Flask(__name__)

name_dict = {
    0: 'Le Signe du Triomphe',
    1: 'Les Vikings',
    2: 'Le Bal des Oiseaux Fantomes',
    3: 'Le Secret de la Lance',
    4: 'Mousquetaire de Richelieu',
    5: 'Le Dernier Panache',
    6: 'Le Mime et L\'Etoile'
}

def get_scores(form):
    scores = []
    for show in name_dict.values():
        scores.append(float(form[f"score_{show}"]))
    return scores

def get_buffer_and_start_end_time(form):
    buffer = int(form["buffer"])
    begin_time = form["begin_time"]
    end_time = form["end_time"]
    if not begin_time:
        begin_time = 0
    else:
        begin_time = hhmm_to_minutes(begin_time)
    if not end_time:
        end_time = 24 * 60  # Default end time if not provided
    else:
        end_time = hhmm_to_minutes(end_time)
    return buffer, begin_time, end_time

def hhmm_to_minutes(time_str):
    hours, minutes = map(int, time_str.split(':'))
    return hours * 60 + minutes

def create_distance_matrix():
    matrix = np.zeros((7, 7))
    distances = [
        [5, 10, 15, 20, 15, 15],
        [5, 10, 15, 10, 10],
        [10, 15, 15, 15],
        [5, 5, 5],
        [5, 5],
        [5]
    ]
    for i in range(len(distances)):
        for j in range(len(distances[i])):
            matrix[i, i+j+1] = distances[i][j]
    matrix += matrix.T
    return matrix

def read_pdf(load_tomorrow=False):
    pdf_url = "https://www.puydufou.com/france/en/program-day/download-tomorrow" if load_tomorrow else "https://www.puydufou.com/france/en/program-day/download-today"
    response = requests.get(pdf_url)
    pdf_filename = "downloaded_file.pdf"
    with open(pdf_filename, "wb") as pdf_file:
        pdf_file.write(response.content)
    with open(pdf_filename, "rb") as pdf_file:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = [page.extract_text() for page in pdf_reader.pages]
    return ''.join(text)

def find_string_in_lines(text, search_string):
    lines = text.splitlines()
    indices = [(line_number, line.find(search_string)) for line_number, line in enumerate(lines) if search_string in line]
    return indices

def get_showtimes(text, begin_time, end_time):
    roman_index = find_string_in_lines(text, "LE SIGNE DU TRIOMPHE35")
    lines = [text.splitlines()[roman_index[0][0]+i] for i in [0, 1, 3, 5, 7, 8, 9]]
    showtimes = [[] for _ in lines]
    for i, show in enumerate(lines):
        times = show.split("'")[-1].split()
        for time in times:
            hours, mins = map(int, time.split(':'))
            minutes = hours * 60 + mins
            if begin_time <= minutes <= end_time:
                showtimes[i].append(minutes)
    return showtimes

def adjust_showtimes(showtimes):
    non_empty_sublists = [sublist for sublist in showtimes if sublist]
    if not non_empty_sublists:
        return None
    
    min_value = min(min(sublist) for sublist in non_empty_sublists)
    for sublist in showtimes:
        for i in range(len(sublist)):
            sublist[i] -= min_value
    return min_value

def find_best_itinerary(durations, distances, showtimes, scores, score_factor, buffer, min_value):
    n = len(durations)
    max_time = 24 * 60
    dp = [[[] for _ in range(max_time + 1)] for _ in range(n)]  # Store itineraries here
    start_times_record = [[None] * (max_time + 1) for _ in range(n)]

    for show in range(n):
        if not showtimes[show]:
            continue  # Skip if there are no showtimes for this show
        for start_time in showtimes[show]:
            end_time = start_time + durations[show]
            if end_time <= max_time:
                dp[show][end_time].append([(show, start_time, end_time)])
                start_times_record[show][end_time] = start_time

    for current_time in range(max_time + 1):
        for show in range(n):
            if not showtimes[show] or not dp[show][current_time]:
                continue  # Skip if there are no showtimes or no valid paths
            for next_show in range(n):
                travel_time = distances[show][next_show] if next_show != show else 0
                if not showtimes[next_show]:
                    continue  # Skip if there are no showtimes for the next show
                for next_start_time in showtimes[next_show]:
                    next_end_time = next_start_time + durations[next_show]
                    if next_start_time >= current_time + travel_time + buffer and next_end_time <= max_time:
                        for itinerary in dp[show][current_time]:
                            new_itinerary = itinerary + [(next_show, next_start_time, next_end_time)]
                            dp[next_show][next_end_time].append(new_itinerary)
                            start_times_record[next_show][next_end_time] = next_start_time

    # Post-process the itineraries to apply score reduction
    max_score = -float('inf')
    best_itinerary = None

    for show in range(n):
        for time in range(max_time + 1):
            for itinerary in dp[show][time]:
                seen_shows = {}
                score = 0
                for (s, _, _) in itinerary:
                    seen_shows[s] = seen_shows.get(s, 0) + 1
                    score += scores[s] / (score_factor ** (seen_shows[s] - 1))
                
                if score > max_score:
                    max_score = score
                    best_itinerary = itinerary

    formatted_itinerary = []
    for (show, start_time, end_time) in best_itinerary:
        start = f"{((start_time + min_value) // 60):02}:{((start_time + min_value) % 60):02}"
        end = f"{((end_time + min_value) // 60):02}:{((end_time + min_value) % 60):02}"
        formatted_itinerary.append((show, start, end))

    return formatted_itinerary

def print_schedule(shows, name_dict, dist_matrix):
    schedule = []
    for i in range(len(shows)):
        show_id, start, end = shows[i]
        show_name = name_dict[show_id]
        schedule.append(f"Watch {show_name} from {start}-{end}")
        if i < len(shows) - 1:
            next_show_id = shows[i + 1][0]
            walk_time = dist_matrix[show_id, next_show_id]
            schedule.append(f"Walk to {name_dict[next_show_id]} ({int(walk_time)} mins)")
    return schedule

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        scores = get_scores(request.form)
        buffer, begin_time, end_time = get_buffer_and_start_end_time(request.form)
        durations = [35, 26, 33, 29, 32, 34, 28]
        distances = create_distance_matrix()
        load_tomorrow = 'load_tomorrow' in request.form
        pdf_text = read_pdf(load_tomorrow)
        showtimes = get_showtimes(pdf_text, begin_time, end_time)
        min_value = adjust_showtimes(showtimes)
        best_itinerary = find_best_itinerary(durations, distances, showtimes, scores, 10, buffer, min_value)
        schedule = print_schedule(best_itinerary, name_dict, distances)
        return render_template('result.html', schedule=schedule)
    return render_template('index.html', name_dict=name_dict)

if __name__ == '__main__':
    app.run(debug=True)
