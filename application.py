import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


"""TODO: store every owned stock in session on login"""
@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    owned = db.execute("SELECT stock_symbol, amount FROM owned WHERE person_id = :id;", id=session["user_id"])
    totalWorth = 0
    total = 0
    for item in owned:
        symbol = item["stock_symbol"]
        amount = item["amount"]

        lookupData = lookup(symbol)

        price = lookupData["price"]
        item["price"] = price

        total = round(amount * price, 2)
        item["total"] = total

        item["name"] = lookupData["name"]

        totalWorth += total
    cash = db.execute("SELECT cash FROM users WHERE id = :id;", id=session["user_id"])[0]["cash"]
    totalWorth += cash
    return render_template("index.html", owned=owned, cash=usd(cash), total=total, totalWorth=usd(totalWorth))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        stock = lookup(request.form.get("symbol"))
        shares = request.form.get("shares")
        try:
            shares = int(shares)
        except ValueError:
            return apology("invalid quantity")
        if stock is None:
            return apology("Could not find your stock")
        elif shares < 1:
            return apology("Please enter a positive quantity")
        else:
            price = stock["price"] * shares
            cash = db.execute("SELECT cash FROM users WHERE id = :id;", id=session["user_id"])
            cashLeft = int(cash[0]["cash"]) - price
            if cashLeft < 0:
                return apology("You don't have enough money")
            db.execute("UPDATE users SET cash = :cashLeft WHERE id = :id;", cashLeft=cashLeft, id=session["user_id"])

            currentHold = db.execute("SELECT amount FROM owned WHERE person_id = :id AND stock_symbol = :symbol;",
                            id=session["user_id"], symbol=stock["symbol"])
            print(currentHold)
            if currentHold:
                db.execute("UPDATE owned SET amount = :newAmount WHERE person_id = :id AND stock_symbol = :symbol;",
                            newAmount=currentHold[0]["amount"]+shares, id=session["user_id"], symbol=stock["symbol"])
            else:
                db.execute("INSERT INTO owned (person_id, stock_symbol, amount) VALUES (:id, :symbol, :amount)",
                            id=session["user_id"], symbol=stock["symbol"], amount=shares)

            db.execute("INSERT INTO history (person_id, stock_symbol, bought, amount, price, time) VALUES (:id, :symbol, :bought, :amount, :price, datetime('now'));",
                        id=session["user_id"], symbol=stock["symbol"], bought=1, amount=shares, price=round(price, 2))
            return redirect("/")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT stock_symbol, amount, price, time, bought FROM history WHERE person_id = :id;", id=session["user_id"])
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")

    # renders results if they typed in a valid stock symbol
    else:
        stock = lookup(request.form.get("stock-symbol"))
        if stock:
            price = usd(stock["price"])
        else:
            price = None
        return render_template("quote.html", stock=stock, price=price)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:

        username = request.form.get("username")
        password = request.form.get("password")
        passwordConfirm = request.form.get("password-confirm")

        # Ensure username was submitted
        if not username:
            return apology("must provide username", 403)

        # Ensure password was submitted and confirmed
        elif not password or not passwordConfirm:
            return apology("must provide password", 403)

        # Apology if username wasn't available
        elif db.execute("SELECT * FROM users WHERE username = :username",
                          username=username):
            return apology("username was already taken", 403)

        # Apology is password and confirmed aren't the same
        elif password != passwordConfirm:
            return apology("your passwords didn't match")

        # If we get here, we're in the clear to enter user into db
        else:
            db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                        username=username, hash=generate_password_hash(password))
            return render_template("login.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    ownedTemp = db.execute("SELECT stock_symbol, amount FROM owned WHERE person_id = :id;", id=session["user_id"])
    owned = {}
    for item in ownedTemp:
        owned[item["stock_symbol"]] = item["amount"]
    if request.method == "GET":
        return render_template("sell.html", owned=owned)
    else:
        stock = request.form.get("stock")
        shares = request.form.get("shares")
        try:
            shares = int(shares)
        except ValueError:
            return apology("invalid quantity")
        if shares < 1 or shares > owned[stock]:
            return apology("invalid quantity")
        elif shares == owned[stock]:
            db.execute("DELETE FROM owned WHERE person_id = :id AND stock_symbol = :symbol;",
                        id=session["user_id"], symbol=stock)
        else:
            db.execute("UPDATE owned SET amount = amount - :shares WHERE person_id = :id AND stock_symbol = :symbol;",
                        shares=shares, id=session["user_id"], symbol=stock)
        price = lookup(stock)["price"]
        print(price)
        profit = price * shares
        #add history item, take away cash
        db.execute("INSERT INTO history ( person_id, stock_symbol, amount, bought, time, price ) VALUES ( :id, :symbol, :amount, 0, datetime('now'), :price);",
                    id=session["user_id"], symbol=stock, amount=shares, price=round(profit, 2))
        db.execute("UPDATE users SET cash = cash + :profit WHERE id = :id;", profit=profit, id=session["user_id"])
        return redirect("/")


@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    """Add funds to account"""
    if request.method == "GET":
        return render_template("add.html")
    else:
        fundsToAdd = request.form.get("cashToAdd")
        try:
            fundsToAdd = float(fundsToAdd)
        except ValueError:
            return apology("invalid amount")
        if fundsToAdd < 0:
            return apology("Enter a positive cash value")
        db.execute("UPDATE users SET cash = cash + :fundsToAdd WHERE id = :id", fundsToAdd=round(fundsToAdd, 2), id=session["user_id"])
        return render_template("add.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
