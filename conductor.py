# Keep it simple!
# 
# "There are two ways of constructing a software design: One way is to make it so simple that there are obviously no deficiencies, and the other way is to make it so complicated that there are no obvious deficiencies." - C.A.R. Hoare

  # TODO:
  # don't create more than one ballot div to interpret (e.g. if you go back and revise an old one)
  # translate from ballot # to batch location
  # feed seed thing in -- get real ballot numbers


import copy
import csv
from datetime import datetime # , isoformat
from flask import Flask, jsonify, request, url_for, send_from_directory, Response
from werkzeug import secure_filename
import os
# https://docs.python.org/3/library/typing.html
from typing import List, Dict

# os.sys.path.append('../RIWAVE/WAVE')
# os.sys.path.append('RIWAVE/WAVE/audit')
os.sys.path.append('RIWAVE/WAVE')
import audit as WAVEaudit
import election as WAVEelection
# import BallotPolling
# self._tolerance

# os.sys.path.append('audit_cvrs/audit_cvrs')
# import rlacalc



# os.sys.path.append('OpenRLA/rivest-sampler-tests')
#from sampler import generate_outputs
# todo: get the sampler from the source instead of OpenRLA's/audit_cvr's copy:
# In the future, replace this with consistent_sampler?:
os.sys.path.append('rivest-sampler-tests/src/sampler')
import sampler

audit_log_dir = 'audit_logs'
if not os.path.exists(audit_log_dir):
   os.makedirs(audit_log_dir)
UPLOAD_FOLDER = 'scratch_files' # better name?
if not os.path.exists(UPLOAD_FOLDER):
   os.makedirs(UPLOAD_FOLDER)


app = Flask(__name__, static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

Interpretation = Dict[str, List[Dict[str, str]]]

# 7r2
# 7s2

# Do we need this, or do we just need the seed?:
#   (Is it repetitive to track this?)

# x = {'y': z}
# 
# def z():
#    print('hi')
# 
# x['y']()

# bp=BallotPolling.BallotPolling()


# In the future, we can have more than one of these running concurrently:
default_audit_state = {
   'all_interpretations': [],
   'seed': None,
   'main_contest_in_progress': None,
   'audit_name': None,
   'audit_type_name': None,
   'ballot_manifest': None,
   # these next two can be gotten from 'ballot_manifest':
   'total_number_of_ballots': None,
   'ballot_ids': None,

   # Hardcoding/configuration, which will come from various CSVs in the future:
   # ("Main" means the one contest we're non-opportunistically auditing):
   # TODO: write-in etc should go here (so we have them in the ballot polling)
   'all_contests': [
      {'id': 'congress_district_1',
       'title': 'Representative in Congress District 1',
       'candidates': ['David N. Cicilline', 'Christopher F. Young']
      },
      {'id': 'assembly_19',
       'title': 'Senator in General Assembly District 19',
       'candidates': ['Alex D. Marszalkowski', 'David M. Chenevert']
      },
      {'id': 'council_at_large',
       'title': 'Town Council At-Large Cumberland',
       'candidates': ['Thomas Kane', 'Peter J. Bradley', 'Charles D. Wilk']
      },
      ],
   'main_contest_id': 'congress_district_1',
   #ballots_cast_for_main_apparent_winner = 600
   # total_main_ballots_cast = 1000
   'main_reported_results': [
      {'candidate': 'David N. Cicilline',
       'percentage': 0.9, # 0.6,
       'votes': 90,
      },
      {'candidate': 'Christopher F. Young',
       'percentage': 0.1, # 0.4,
       'votes': 10,
      },
      ],
   }

audit_state = copy.deepcopy(default_audit_state)







def call_f(f, *args, **kwargs):
    # TODO: log instead of print:
    print(tuple((datetime.now().isoformat(), f.__name__, args, kwargs)))
    f(*args, **kwargs)

# example usage:
def test_0(a, b, c):
    print(a*b+c)
call_f(test_0, 4, 5, 6)
call_f(test_0, c=4, b=5, a=6)


def make_contestant(name):
    return WAVEelection.Contestant(ID=name, name=name)

# TODO: type:
def make_result(all_contestants, result_dict):
    # TODO: we construct these candidates here. Make sure there are
    #   no issues with pointer equality from creating them twice:
    contestant = all_contestants[result_dict['candidate']]
    return WAVEelection.Result(contestant=contestant, percentage=result_dict['percentage'], votes=result_dict['votes'])

def make_ballot(all_contestants, interpretation):
    ballot = WAVEelection.Ballot()
    #ballot.set_audit_seq_num(i+1)
    #ballot.get_physical_ballot_num(i+1):
    # interp {'ballot_id': 9104, 'contests': {'congress_district_1': 'David N. Cicilline', 'assembly_19': 'David M. Chenevert', 'council_at_large': 'Peter J. Bradley'}}
    # ballot.set_reported_value(yes) # for ballot comparison
    ballot.set_actual_value(all_contestants[interpretation['contests'][audit_state['main_contest_id']]])
    return ballot

# TODO: type:
def get_ballot_polling_results():
    bp = WAVEaudit.BallotPolling()
    # contest = contests[main_contest_id]
    # TODO: 'contests' should probably be a dict instead:
    contest = list(filter(lambda c: c['id'] == audit_state['main_contest_id'], audit_state['all_contests']))[0]

    # TODO: clean up how we do this. This is just a quick way to
    #   make sure we have all options since there may be ones not
    #   in the contest description (e.g. write-ins, or "no
    #   selection"):
    all_contestant_names = list(set(contest['candidates']).union({ i['contests'][audit_state['main_contest_id']] for i in audit_state['all_interpretations']}))

    all_contestants = { name: make_contestant(name) for name in all_contestant_names }
    reported_results = [ make_result(all_contestants, r) for r in audit_state['main_reported_results'] ]

    bp.init(results=reported_results, ballot_count=100)
    bp.set_parameters([1]) # this is a tolerance of 1%
    ballots = [ make_ballot(all_contestants, i) for i in audit_state['all_interpretations'] ]
    bp.recompute(results=reported_results, ballots=ballots)
    return(jsonify({'status': bp.get_status(), 'progress': bp.get_progress()}))

audit_types = {
    'ballot_polling': {
        'get_results': get_ballot_polling_results,
        'init': None,
        },
    }


@app.route('/get-audit-types')
def get_audit_types():
    return jsonify({'types': list(audit_types.keys())})

@app.route('/set-audit-type', methods=['POST'])
def set_audit_type():
    data = request.get_json()
    if 'type' in data:
        if data['type'] in audit_types:
            global audit_state
            audit_state['audit_type_name'] = data['type']
            t = audit_types[data['type']]
            return ''
        else:
            return "That audit type isn't a choice", 422
    else:
        return 'Key "type" not present in request', 422

@app.route('/set-audit-name', methods=['POST'])
def set_audit_name():
    data = request.get_json()
    if 'audit_name' in data:
        global audit_state
        audit_state['audit_name'] = data['audit_name']
        return ''
    else:
        return 'Key "audit_name" not present in request', 422

@app.route('/get-contests')
def route_get_contests():
    return jsonify({'contests': audit_state['all_contests']})

@app.route('/add-interpretation', methods=['POST'])
def add():
   data = request.get_json()
   app.logger.debug(data)
   if 'interpretation' in data:
      global audit_state
      audit_state['all_interpretations'].append(data['interpretation'])
      return ''
   else:
      return 'Key "interpretation" is not present in the request', 422

@app.route('/get-all-interpretations')
def get_all_interpretations():
   # global audit_state
   return str((audit_state['all_interpretations'])) # , bp._ballot_count, seed))

@app.route('/get-audit-state', methods=['GET', 'POST'])
def get_audit_state():
   return jsonify(audit_state)

@app.route('/set-seed', methods=['POST'])
def set_seed():
   j = request.get_json()
   if 'seed' in j:
      global audit_state
      # global seed
      # global main_contest_in_progress
      audit_state['seed'] = j['seed']


      # TODO: un-hardcode these values (or set them to the 'real' hardcoded ones):
      # TODO: can someone double-check values of 'a' and 'b'
      [], audit_state['ballot_ids'] = sampler.generate_outputs(seed=audit_state['seed'], with_replacement=False, n=6,a=1,b=audit_state['total_number_of_ballots'],skip=0)
      return jsonify({'ballot_ids': audit_state['ballot_ids']}) # TODO: do we want to return anything here?
   else:
      return 'Key "seed" is not present', 422


@app.route('/get-ballot-ids')
def get_ballot_ids():
    return jsonify({'ballot_ids': audit_state['ballot_ids']})

@app.route('/ballot-pull-sheet.txt')
def get_ballot_pull_sheet():
    s = 'Ballot Pull Sheet\n\n'
    s += 'Ballot Order:\n'
    s += '\n'.join([ '{}. {}'.format(i,v) for i, v in enumerate(audit_state['ballot_ids'], 1) ])
    s += '\n\nSorted Order:\n'
    s += '\n'.join([ '{}. {}'.format(i,v) for i, v in enumerate(sorted(audit_state['ballot_ids']), 1) ])
    # TODO: content-type: text/plain
    return Response(s, mimetype='text/plain')


### "Interpretation handlers"
# (Not git-adding yet)
@app.route('/get-audit-status', methods=['POST'])
def get_audit_status():
    # print(contest_type_name)
    # print(contest_types[contest_type_name])
    x = audit_types[audit_state['audit_type_name']]['get_results']()
    print(x)
    return x


@app.route('/upload-ballot-manifest', methods=['POST'])
def upload_ballot_manifest():
    # "Be conservative in what you send, be liberal in what you accept"
    # TODO: for transparency, also return the file's hash
    if 'file' not in request.files:
        return 'File not uploaded', 400
    file = request.files['file']
    # "if user does not select file, browser also"
    # "submit an empty part without filename"
    if file.filename == '':
        return 'No selected file', 400
    if file: # and allowed_file(file.filename):
        filename = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
        file.save(filename)
        with open(filename, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = [ {'batch_id': r['Batch ID'], 'num_sheets': int(r['# of Sheets']), 'first_imprinted_id': int(r['First Imprinted ID'])} for r in reader ]
            global audit_state
            audit_state['total_number_of_ballots'] = sum([ r['num_sheets'] for r in rows ])
            audit_state['ballot_manifest'] = rows
            # TODO: data integrity checks!
            # both for matching with CVR data (counts etc), and with the counts (first_printed_id adds to num_sheets etc)
            return jsonify(rows) # todo: don't return this?

@app.route('/reset-audit-state', methods=['POST'])
def reset_audit_state():
    global audit_state
    audit_state = copy.deepcopy(default_audit_state)
    return ''

@app.route('/reset')
def send_reset_page():
    return send_from_directory('ui', 'reset_page.html')


### Static files
@app.route('/jquery.js')
def jquery():
   # We only use this for '$.ajax'; remove?:
   return app.send_static_file('jquery-3.3.1.min.js')
@app.route('/rla_ui.js')
def rla_ui_js():
   return send_from_directory('ui','rla_ui.js')
@app.route('/style.css')
def style_css():
   return send_from_directory('ui','style.css')
@app.route('/')
def index():
   return send_from_directory('ui','index.html')

