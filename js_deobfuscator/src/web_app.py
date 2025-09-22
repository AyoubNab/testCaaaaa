import os
from flask import Flask, render_template, request
from deobfuscator import deobfuscate

# Configure the Flask app
# We need to tell it where to find the 'templates' and 'static' folders.
# The paths are relative to the project root 'js_deobfuscator'.
app = Flask(__name__, template_folder='../templates', static_folder='../static')

@app.route('/', methods=['GET', 'POST'])
def index():
    obfuscated_code = ''
    deobfuscated_code = ''
    if request.method == 'POST':
        obfuscated_code = request.form.get('obfuscated_code', '')
        if obfuscated_code:
            # The deobfuscate function now returns only the deobfuscated code.
            deobfuscated_code = deobfuscate(obfuscated_code)

    return render_template('index.html', obfuscated_code=obfuscated_code, deobfuscated_code=deobfuscated_code)

if __name__ == '__main__':
    # Using 0.0.0.0 to make it accessible from outside the container
    app.run(host='0.0.0.0', port=8080, debug=True)
