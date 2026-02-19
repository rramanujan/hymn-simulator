## HYMN Simulator

A web-based simulator for a small hypothetical CPU ("HYMN machine"), originally conceived and designed by [Carl Burch](https://cburch.com/), with:

- Assembly code editing in the browser
- Interactive memory/register bit editing
- Step-by-step or full-program execution
- Input/output support (`read` / `write`)
- Per-user execution sessions

The backend is a Flask API, and the frontend is a static single-page app.

### Project Structure

- `app.py`: Flask app and API endpoints (`/api/*`)
- `simulator.py`: CPU + assembler implementation
- `static/index.html`: main UI
- `static/docs.html`: instruction/reference docs page
- `test_app.py`: backend regression tests

### Requirements

- Python 3.9+
- Dependencies in `requirements.txt`

### Run Locally

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start the server:

```bash
python app.py
```

3. Open: [http://localhost:5000](http://localhost:5000)


### Developers

* [Carl Burch](https://cburch.com/)
* [Raghu Ramanujan](https://www.davidson.edu/people/raghu-ramanujan)
* [Murtaza Nikzad](https://www.murtazanikzad.com/) '27