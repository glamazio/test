from . import db
from datetime import datetime, date, time, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
# If using Flask-Login
# from flask_login import UserMixin

# Example User model (if you need authentication for accessing the app)
# class User(UserMixin, db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     username = db.Column(db.String(64), index=True, unique=True)
#     email = db.Column(db.String(120), index=True, unique=True)
#     password_hash = db.Column(db.String(256)) # Increased length for stronger hashing
#     is_admin = db.Column(db.Boolean, default=False)

#     def set_password(self, password):
#         self.password_hash = generate_password_hash(password)

#     def check_password(self, password):
#         return check_password_hash(self.password_hash, password)

#     def __repr__(self):
#         return f'<User {self.username}>'


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(255))
    employees = db.relationship('Employee', backref='role', lazy='dynamic')

    def __repr__(self):
        return f'<Role {self.name}>'


class Employee(db.Model):
    __tablename__ = 'employees'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(64), nullable=False)
    last_name = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=True) # Optional email
    phone_number = db.Column(db.String(20), nullable=True) # Optional phone
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    # Availability: Storing as JSON. Could be a separate table for more complex queries.
    # Example: {"monday": ["09:00-12:00", "13:00-17:00"], "tuesday": [...]}
    # For 30-min intervals, this might become very granular.
    # Simpler approach for now: store general availability notes or link to a more complex system.
    # For this iteration, let's assume availability is managed externally or via a simpler text field.
    availability_notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    shifts = db.relationship('Shift', backref='employee', lazy='dynamic')
    time_logs = db.relationship('TimeLog', backref='employee', lazy='dynamic')

    def __repr__(self):
        return f'<Employee {self.first_name} {self.last_name}>'

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class StoreHours(db.Model):
    __tablename__ = 'store_hours'
    id = db.Column(db.Integer, primary_key=True)
    # weekday: 0=Monday, 1=Tuesday, ..., 6=Sunday
    weekday = db.Column(db.Integer, nullable=False, unique=True) # Ensures one entry per day
    open_time = db.Column(db.Time, nullable=True) # Nullable if closed on this day
    close_time = db.Column(db.Time, nullable=True) # Nullable if closed on this day
    lunch_break_start = db.Column(db.Time, nullable=True)
    lunch_break_end = db.Column(db.Time, nullable=True)
    is_closed = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        day_map = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_name = day_map[self.weekday] if self.weekday is not None else "N/A"
        if self.is_closed:
            return f'<StoreHours {day_name}: Closed>'
        return f'<StoreHours {day_name}: {self.open_time}-{self.close_time}>'

    @staticmethod
    def initialize_hours():
        for i in range(7):
            if not StoreHours.query.filter_by(weekday=i).first():
                store_day = StoreHours(
                    weekday=i,
                    is_closed=(i >= 5) # Default Saturday and Sunday to closed
                )
                if not (i >= 5): # If weekday
                    store_day.open_time = time(9,0)
                    store_day.close_time = time(18,0)
                    store_day.lunch_break_start = time(12,30)
                    store_day.lunch_break_end = time(13,30)
                db.session.add(store_day)
        db.session.commit()


class Shift(db.Model):
    __tablename__ = 'shifts'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    shift_date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Shift ID {self.id} for {self.employee.full_name} on {self.shift_date} from {self.start_time} to {self.end_time}>'

    @property
    def duration(self):
        if self.start_time and self.end_time:
            # Combine date and time to create datetime objects for subtraction
            start_dt = datetime.combine(self.shift_date, self.start_time)
            end_dt = datetime.combine(self.shift_date, self.end_time)
            if end_dt < start_dt: # Handles overnight shifts if date is not changed
                end_dt += timedelta(days=1)
            return end_dt - start_dt
        return timedelta(0)

    @property
    def duration_hours(self):
        return self.duration.total_seconds() / 3600


class TimeLog(db.Model):
    __tablename__ = 'time_logs'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id'), nullable=True) # Link to scheduled shift
    clock_in_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    clock_out_time = db.Column(db.DateTime, nullable=True, index=True)
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<TimeLog ID {self.id} for {self.employee.full_name} - In: {self.clock_in_time} Out: {self.clock_out_time}>'

    @property
    def worked_duration(self):
        if self.clock_in_time and self.clock_out_time:
            return self.clock_out_time - self.clock_in_time
        elif self.clock_in_time and not self.clock_out_time: # Still clocked in
            return datetime.utcnow() - self.clock_in_time
        return timedelta(0)

    @property
    def worked_hours(self):
        return self.worked_duration.total_seconds() / 3600

# Placeholder for User model if you decide to add full authentication later
class User(db.Model): # Add UserMixin from flask_login if using it
    __tablename__ = 'users' # Explicitly naming the table
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)
    # Add any other fields you need for users, e.g., created_at, last_login

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if self.password_hash:
            return check_password_hash(self.password_hash, password)
        return False

    def __repr__(self):
        return f'<User {self.username}>'
