# JavaScript Deobfuscator

This is a Python script that attempts to deobfuscate JavaScript code by applying a series of transformations. It uses an Abstract Syntax Tree (AST) based approach to analyze and modify the code safely.

## Features

The script can perform the following deobfuscation tasks:

-   **String Array Resolution**: Detects and resolves the common pattern where strings are hidden in an array and accessed by a wrapper function. It can even handle simple array "shuffling" functions.
-   **Variable Renaming**: Renames obfuscated variables (e.g., `_0xabc123`, `l1lI`, `O0`) to a clean, sequential format (`var_0`, `var_1`, etc.) while respecting variable scopes.
-   **Expression Simplification**: Performs constant folding on simple expressions. For example, `2 + 3` becomes `5`, and `'a' + 'b'` becomes `'ab'`.
-   **Dead Code Elimination**:
    -   Removes `if` statements with constant `true`/`false` conditions.
    -   Removes unused function and variable declarations.
-   **Reporting**: Generates a report at the top of the deobfuscated code detailing variable usage counts and the most frequently used string array indexes.
-   **Code Formatting**: The final output is automatically formatted using `jsbeautifier` for readability.

## Installation

The script uses a few Python libraries. You can install them using the provided `requirements.txt` file.

1.  Make sure you have Python 3 and `pip` installed.
2.  Navigate to the `js_deobfuscator` directory.
3.  Run the following command:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

The script is run from the command line and takes two arguments: the input file path and the output file path.

Navigate to the `js_deobfuscator` directory.

```bash
python src/deobfuscator.py <path_to_input.js> <path_to_output.js>
```

**Example:**

```bash
python src/deobfuscator.py samples/sample_obfuscated.js samples/sample_deobfuscated.js
```

## Web Interface

In addition to the command-line tool, this project includes a simple web interface built with Flask.

### Running the Web App

#### For Windows Users (Easy Way)

Simply navigate to the `js_deobfuscator` directory and double-click the `start_web_app.bat` file.

It will automatically check for dependencies, install them if needed, and launch the web server.

#### Manual Installation (All Platforms)

1.  Make sure you have installed all dependencies (`pip install -r requirements.txt`).
2.  Navigate to the `js_deobfuscator` directory.
3.  Run the web application:
    ```bash
    python src/web_app.py
    ```
4.  Open your web browser and go to `http://127.0.0.1:8080`.

You can then paste your obfuscated code into the left text area and click "Deobfuscate" to see the result on the right.

## How It Works

The deobfuscator works by parsing the source JavaScript into an Abstract Syntax Tree (AST) using the `esprima` library. An AST is a tree representation of the code's structure.

The script then runs a series of "passes" over this tree. Each pass is a visitor class that traverses the AST and performs a specific transformation:

1.  **StringArrayPass**: Finds and resolves string arrays.
2.  **VariableRenamer**: Renames variables.
3.  **ExpressionSimplifier**: Folds constant expressions.
4.  **DeadCodeEliminator**: Removes unused code.
5.  **UsageCounter**: Counts variable uses for the final report.

After all transformations are complete, the modified AST is converted back into JavaScript code using the `escodegen` library, and the final result is formatted for readability.
