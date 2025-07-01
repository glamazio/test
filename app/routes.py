from flask import render_template, request, redirect, url_for, flash, jsonify, current_app, Blueprint
from . import db # . significa dal package corrente (app)
from .models import Employee, Role, StoreHours, Shift, TimeLog, User # Assicurati che User sia importato se usato
from datetime import datetime, time, date, timedelta
import sys # Per python_version in settings
import flask # Per flask_version in settings
import os # Per os.path.basename in settings

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    """Dashboard principale."""
    today = date.today()

    todays_shifts = Shift.query.filter(Shift.shift_date == today).order_by(Shift.start_time).all()

    critical_alerts = []
    if not todays_shifts:
        critical_alerts.append(f"Nessun turno programmato per oggi ({today.strftime('%A, %d %B %Y')}).")

    clocked_in_now = TimeLog.query.filter(TimeLog.clock_out_time == None).all()
    active_employees_list = Employee.query.filter_by(is_active=True).order_by(Employee.last_name).all()

    return render_template('dashboard.html',
                           todays_shifts=todays_shifts,
                           critical_alerts=critical_alerts,
                           current_date=today,
                           clocked_in_now=clocked_in_now,
                           active_employees=active_employees_list)

@bp.route('/schedule', methods=['GET', 'POST'])
def manage_schedule():
    days = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    if request.method == 'POST':
        try:
            for i in range(7):
                day_data = StoreHours.query.filter_by(weekday=i).first()
                if not day_data:
                    day_data = StoreHours(weekday=i)
                    db.session.add(day_data)

                is_closed = request.form.get(f'is_closed_{i}') == 'on'
                day_data.is_closed = is_closed

                if not is_closed:
                    open_time_val = request.form.get(f'open_time_{i}')
                    close_time_val = request.form.get(f'close_time_{i}')
                    lunch_start_val = request.form.get(f'lunch_start_{i}')
                    lunch_end_val = request.form.get(f'lunch_end_{i}')

                    day_data.open_time = datetime.strptime(open_time_val, '%H:%M').time() if open_time_val else None
                    day_data.close_time = datetime.strptime(close_time_val, '%H:%M').time() if close_time_val else None
                    day_data.lunch_break_start = datetime.strptime(lunch_start_val, '%H:%M').time() if lunch_start_val else None
                    day_data.lunch_break_end = datetime.strptime(lunch_end_val, '%H:%M').time() if lunch_end_val else None

                    if day_data.open_time and day_data.close_time and day_data.close_time <= day_data.open_time:
                        flash(f"Per {days[i]}, l'orario di chiusura deve essere successivo all'apertura.", "warning")
                        # Potrebbe essere necessario un rollback o una gestione più fine degli errori qui
                else:
                    day_data.open_time = None
                    day_data.close_time = None
                    day_data.lunch_break_start = None
                    day_data.lunch_break_end = None
            db.session.commit()
            flash('Orari del negozio aggiornati con successo!', 'success')
        except ValueError as ve:
            db.session.rollback()
            flash(f"Errore nel formato dell'ora: {ve}. Usare HH:MM.", 'danger')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating schedule: {e}")
            flash(f"Errore durante l'aggiornamento degli orari: {e}", 'danger')
        return redirect(url_for('main.manage_schedule'))

    store_hours_list = StoreHours.query.order_by(StoreHours.weekday).all()
    if len(store_hours_list) < 7:
        StoreHours.initialize_hours()
        store_hours_list = StoreHours.query.order_by(StoreHours.weekday).all()

    all_store_hours = [None]*7
    for sh_item in store_hours_list:
        all_store_hours[sh_item.weekday] = sh_item

    # Se initialize_hours non ha committato o se ci sono ancora buchi per qualche motivo
    for i in range(7):
        if all_store_hours[i] is None:
            # Questo è un fallback, initialize_hours dovrebbe gestire la creazione
            current_app.logger.warn(f"StoreHours per weekday {i} mancante, creando fallback.")
            fallback_sh = StoreHours(weekday=i, is_closed=True) # default a chiuso
            db.session.add(fallback_sh)
            all_store_hours[i] = fallback_sh
            try:
                db.session.commit() # Commit singolo per fallback
            except Exception as e_commit:
                db.session.rollback()
                current_app.logger.error(f"Errore nel commit del fallback StoreHours: {e_commit}")


    return render_template('manage_schedule.html', store_hours=all_store_hours, days=days)


@bp.route('/employees', methods=['GET', 'POST'])
def manage_employees():
    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'add_employee':
                first_name = request.form.get('first_name')
                last_name = request.form.get('last_name')
                email = request.form.get('email')
                phone_number = request.form.get('phone_number')
                role_id = request.form.get('role_id')
                availability_notes = request.form.get('availability_notes')

                if not first_name or not last_name:
                    flash('Nome e Cognome sono obbligatori.', 'warning')
                else:
                    new_employee = Employee(
                        first_name=first_name, last_name=last_name,
                        email=email if email else None, phone_number=phone_number if phone_number else None,
                        role_id=int(role_id) if role_id else None,
                        availability_notes=availability_notes
                    )
                    db.session.add(new_employee)
                    db.session.commit()
                    flash('Dipendente aggiunto con successo!', 'success')

            elif action == 'edit_employee':
                employee_id = request.form.get('employee_id')
                employee = Employee.query.get_or_404(employee_id)
                employee.first_name = request.form.get('first_name', employee.first_name)
                employee.last_name = request.form.get('last_name', employee.last_name)
                employee.email = request.form.get('email', employee.email)
                employee.phone_number = request.form.get('phone_number', employee.phone_number)
                employee.role_id = int(request.form.get('role_id')) if request.form.get('role_id') else None
                employee.availability_notes = request.form.get('availability_notes', employee.availability_notes)
                employee.is_active = request.form.get('is_active') == 'on'
                db.session.commit()
                flash('Dipendente aggiornato con successo!', 'success')

            elif action == 'add_role':
                role_name = request.form.get('role_name')
                role_description = request.form.get('role_description')
                if role_name:
                    existing_role = Role.query.filter(Role.name.ilike(role_name)).first()
                    if existing_role:
                        flash(f"Il ruolo '{role_name}' esiste già.", 'warning')
                    else:
                        new_role = Role(name=role_name, description=role_description)
                        db.session.add(new_role)
                        db.session.commit()
                        flash('Ruolo aggiunto con successo!', 'success')
                else:
                    flash('Il nome del ruolo è obbligatorio.', 'warning')

            elif action == 'delete_employee':
                employee_id = request.form.get('delete_employee_id')
                employee_to_delete = Employee.query.get_or_404(employee_id)
                if Shift.query.filter_by(employee_id=employee_id).first() or \
                   TimeLog.query.filter_by(employee_id=employee_id).first():
                     flash(f"Impossibile eliminare {employee_to_delete.full_name} perché ha turni o registrazioni associate. Considera di renderlo inattivo.", 'warning')
                else:
                    db.session.delete(employee_to_delete)
                    db.session.commit()
                    flash('Dipendente eliminato con successo!', 'success')

            elif action == 'delete_role':
                role_id = request.form.get('delete_role_id')
                role_to_delete = Role.query.get_or_404(role_id)
                if role_to_delete.employees.count() > 0:
                    flash(f"Impossibile eliminare il ruolo '{role_to_delete.name}' perchè è assegnato a dei dipendenti.", 'warning')
                else:
                    db.session.delete(role_to_delete)
                    db.session.commit()
                    flash('Ruolo eliminato con successo!', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error in manage_employees: {e}")
            flash(f"Si è verificato un errore: {e}", "danger")
        return redirect(url_for('main.manage_employees'))

    employees = Employee.query.order_by(Employee.last_name, Employee.first_name).all()
    roles = Role.query.order_by(Role.name).all()
    return render_template('manage_employees.html', employees=employees, roles=roles)

@bp.route('/shifts', methods=['GET'])
def view_shifts():
    date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = date.today()
        flash("Formato data non valido, visualizzazione per oggi.", "warning")

    employee_id_str = request.args.get('employee_id', 'all')

    start_of_week = selected_date - timedelta(days=selected_date.weekday())
    week_dates = [start_of_week + timedelta(days=i) for i in range(7)]

    shifts_for_week_query = Shift.query.join(Employee).filter(
        Shift.shift_date >= week_dates[0],
        Shift.shift_date <= week_dates[-1]
    ).order_by(Shift.shift_date, Shift.start_time, Employee.last_name)

    selected_employee_id_int = None
    if employee_id_str and employee_id_str != 'all':
        try:
            selected_employee_id_int = int(employee_id_str)
            shifts_for_week_query = shifts_for_week_query.filter(Shift.employee_id == selected_employee_id_int)
        except ValueError:
            flash("ID dipendente non valido nel filtro.", "warning")
            employee_id_str = 'all'

    shifts_for_week_list = shifts_for_week_query.all()

    shifts_by_day = {day: [] for day in week_dates}
    for shift_item in shifts_for_week_list:
        shifts_by_day[shift_item.shift_date].append(shift_item)

    employees = Employee.query.filter_by(is_active=True).order_by(Employee.last_name).all()

    return render_template('view_shifts.html',
                           selected_date=selected_date,
                           employees=employees,
                           selected_employee_id=selected_employee_id_int,
                           week_dates=week_dates,
                           shifts_by_day=shifts_by_day,
                           str=str,
                           date_to_str=lambda d: d.strftime('%Y-%m-%d'),
                           time_to_str=lambda t: t.strftime('%H:%M'),
                           date=date # Passare il modulo date per date.today() nel template
                           )


@bp.route('/shifts/new', methods=['GET', 'POST'])
def create_shift():
    if request.method == 'POST':
        try:
            employee_id = request.form.get('employee_id')
            shift_date_str = request.form.get('shift_date')
            start_time_str = request.form.get('start_time')
            end_time_str = request.form.get('end_time')
            notes = request.form.get('notes')

            if not all([employee_id, shift_date_str, start_time_str, end_time_str]):
                flash('Dipendente, data, ora inizio e ora fine sono obbligatori.', 'warning')
            else:
                shift_date_obj = datetime.strptime(shift_date_str, '%Y-%m-%d').date()
                start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()
                end_time_obj = datetime.strptime(end_time_str, '%H:%M').time()

                if end_time_obj <= start_time_obj:
                    flash("L'ora di fine deve essere successiva all'ora di inizio.", "warning")
                else:
                    # TODO: Validazioni avanzate (orari negozio, sovrapposizioni)
                    new_shift = Shift(
                        employee_id=int(employee_id), shift_date=shift_date_obj,
                        start_time=start_time_obj, end_time=end_time_obj, notes=notes
                    )
                    db.session.add(new_shift)
                    db.session.commit()
                    flash('Turno creato con successo!', 'success')
                    return redirect(url_for('main.view_shifts', date=shift_date_str))
        except ValueError:
            flash("Formato data o ora non valido.", "danger")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating shift: {e}")
            flash(f"Errore durante la creazione del turno: {e}", "danger")
        return redirect(url_for('main.create_shift', date=request.form.get('shift_date', date.today().strftime('%Y-%m-%d'))))

    shift_date_param = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    try:
        initial_date = datetime.strptime(shift_date_param, '%Y-%m-%d').date()
    except ValueError:
        initial_date = date.today()

    employees = Employee.query.filter_by(is_active=True).order_by(Employee.last_name).all()
    time_slots = [time(h, m).strftime('%H:%M') for h in range(24) for m in (0, 30)]

    return render_template('create_edit_shift.html',
                           form_action_url=url_for('main.create_shift'),
                           form_title="Crea Nuovo Turno",
                           employees=employees, shift_data=None,
                           time_slots=time_slots,
                           initial_date_str=initial_date.strftime('%Y-%m-%d'))

@bp.route('/shifts/edit/<int:shift_id>', methods=['GET', 'POST'])
def edit_shift(shift_id):
    shift_to_edit = Shift.query.get_or_404(shift_id)
    if request.method == 'POST':
        try:
            shift_to_edit.employee_id = int(request.form.get('employee_id'))
            new_date_str = request.form.get('shift_date')
            shift_to_edit.shift_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
            shift_to_edit.start_time = datetime.strptime(request.form.get('start_time'), '%H:%M').time()
            shift_to_edit.end_time = datetime.strptime(request.form.get('end_time'), '%H:%M').time()
            shift_to_edit.notes = request.form.get('notes')

            if shift_to_edit.end_time <= shift_to_edit.start_time:
                 flash("L'ora di fine deve essere successiva all'ora di inizio.", "warning")
            else:
                # TODO: Validazioni avanzate
                db.session.commit()
                flash('Turno aggiornato con successo!', 'success')
                return redirect(url_for('main.view_shifts', date=new_date_str))
        except ValueError:
            flash("Formato data o ora non valido.", "danger")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error editing shift {shift_id}: {e}")
            flash(f"Errore durante l'aggiornamento del turno: {e}", "danger")
        return redirect(url_for('main.edit_shift', shift_id=shift_id))

    employees = Employee.query.filter_by(is_active=True).order_by(Employee.last_name).all()
    time_slots = [time(h, m).strftime('%H:%M') for h in range(24) for m in (0, 30)]
    shift_data = {
        'employee_id': shift_to_edit.employee_id,
        'shift_date': shift_to_edit.shift_date.strftime('%Y-%m-%d'),
        'start_time': shift_to_edit.start_time.strftime('%H:%M'),
        'end_time': shift_to_edit.end_time.strftime('%H:%M'),
        'notes': shift_to_edit.notes
    }
    return render_template('create_edit_shift.html',
                           form_action_url=url_for('main.edit_shift', shift_id=shift_id),
                           form_title="Modifica Turno",
                           employees=employees, shift_data=shift_data,
                           time_slots=time_slots,
                           initial_date_str=shift_to_edit.shift_date.strftime('%Y-%m-%d'))


@bp.route('/shifts/delete/<int:shift_id>', methods=['POST'])
def delete_shift(shift_id):
    shift_to_delete = Shift.query.get_or_404(shift_id)
    shift_date_str = shift_to_delete.shift_date.strftime('%Y-%m-%d')
    try:
        db.session.delete(shift_to_delete)
        db.session.commit()
        flash('Turno eliminato con successo!', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting shift {shift_id}: {e}")
        flash(f"Errore durante l'eliminazione del turno: {e}", "danger")
    return redirect(url_for('main.view_shifts', date=shift_date_str))


@bp.route('/timelogs', methods=['GET', 'POST'])
def manage_time_logs():
    redirect_date_val = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    redirect_employee_id_val = request.args.get('employee_id')

    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'clock_in':
                employee_id = request.form.get('employee_id')
                if not employee_id:
                    flash("Selezionare un dipendente per la timbratura.", "warning")
                else:
                    existing_log = TimeLog.query.filter_by(employee_id=employee_id, clock_out_time=None).first()
                    if existing_log:
                        flash(f"{existing_log.employee.full_name} è già timbrato in entrata.", "warning")
                    else:
                        new_log = TimeLog(employee_id=employee_id, clock_in_time=datetime.utcnow())
                        db.session.add(new_log)
                        db.session.commit()
                        flash(f"{new_log.employee.full_name} timbrato in entrata.", "success")

            elif action == 'clock_out':
                employee_id = request.form.get('employee_id')
                if not employee_id:
                     flash("ID dipendente non specificato per la timbratura in uscita.", "warning")
                else:
                    log_to_close = TimeLog.query.filter_by(employee_id=employee_id, clock_out_time=None).order_by(TimeLog.clock_in_time.desc()).first()
                    if log_to_close:
                        log_to_close.clock_out_time = datetime.utcnow()
                        db.session.commit()
                        flash(f"{log_to_close.employee.full_name} timbrato in uscita.", "success")
                    else:
                        flash("Nessuna timbratura di entrata attiva trovata per questo dipendente.", "warning")

            elif action == 'add_manual_log':
                employee_id = request.form.get('manual_employee_id')
                clock_in_str = request.form.get('manual_clock_in')
                clock_out_str = request.form.get('manual_clock_out')
                notes = request.form.get('manual_notes')

                if not all([employee_id, clock_in_str, clock_out_str]):
                    flash("Dipendente, data/ora di entrata e data/ora di uscita sono obbligatori.", "warning")
                else:
                    clock_in_dt = datetime.fromisoformat(clock_in_str)
                    clock_out_dt = datetime.fromisoformat(clock_out_str)
                    if clock_out_dt <= clock_in_dt:
                        flash("L'ora di uscita deve essere successiva all'ora di entrata.", "warning")
                    else:
                        manual_log = TimeLog(
                            employee_id=employee_id, clock_in_time=clock_in_dt,
                            clock_out_time=clock_out_dt, notes=notes
                        )
                        db.session.add(manual_log)
                        db.session.commit()
                        flash("Registrazione manuale aggiunta.", "success")
                        redirect_date_val = clock_in_dt.strftime('%Y-%m-%d')

            elif action == 'edit_log':
                log_id = request.form.get('log_id')
                log_to_edit = TimeLog.query.get_or_404(log_id)
                clock_in_str = request.form.get(f'edit_clock_in_{log_id}')
                clock_out_str = request.form.get(f'edit_clock_out_{log_id}')
                notes = request.form.get(f'edit_notes_{log_id}')

                if clock_in_str: log_to_edit.clock_in_time = datetime.fromisoformat(clock_in_str)
                if clock_out_str: log_to_edit.clock_out_time = datetime.fromisoformat(clock_out_str)
                else: log_to_edit.clock_out_time = None
                log_to_edit.notes = notes

                if log_to_edit.clock_out_time and log_to_edit.clock_in_time >= log_to_edit.clock_out_time:
                    flash("L'ora di uscita deve essere successiva all'ora di entrata.", "warning")
                    db.session.rollback()
                else:
                    db.session.commit()
                    flash(f"Registrazione ID {log_id} aggiornata.", "success")
                    redirect_date_val = log_to_edit.clock_in_time.strftime('%Y-%m-%d')

            elif action == 'delete_log':
                log_id = request.form.get('log_id_delete')
                log_to_delete = TimeLog.query.get_or_404(log_id)
                redirect_date_val = log_to_delete.clock_in_time.strftime('%Y-%m-%d')
                db.session.delete(log_to_delete)
                db.session.commit()
                flash(f"Registrazione ID {log_id} eliminata.", "success")

        except ValueError as ve:
            flash(f"Formato data/ora non valido: {ve}. Usare YYYY-MM-DDTHH:MM.", "danger")
            db.session.rollback()
        except Exception as e:
            current_app.logger.error(f"Error in manage_time_logs: {e}")
            flash(f"Si è verificato un errore: {e}", "danger")
            db.session.rollback()

        return redirect(url_for('main.manage_time_logs', date=redirect_date_val, employee_id=redirect_employee_id_val))

    # GET request
    selected_date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    try:
        selected_date_obj = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date_obj = date.today()
        flash("Formato data non valido, visualizzazione per oggi.", "warning")

    employee_id_filter = request.args.get('employee_id', 'all')
    start_of_day_dt = datetime.combine(selected_date_obj, time.min)
    end_of_day_dt = datetime.combine(selected_date_obj, time.max)

    time_logs_query = TimeLog.query.filter(
        TimeLog.clock_in_time >= start_of_day_dt,
        TimeLog.clock_in_time <= end_of_day_dt
    ).order_by(TimeLog.clock_in_time.desc())

    selected_employee_id_int = None
    if employee_id_filter and employee_id_filter != 'all':
        try:
            selected_employee_id_int = int(employee_id_filter)
            time_logs_query = time_logs_query.filter(TimeLog.employee_id == selected_employee_id_int)
        except ValueError:
            flash("ID dipendente non valido.", "warning")

    time_logs = time_logs_query.all()
    active_employees = Employee.query.filter_by(is_active=True).order_by(Employee.last_name).all()
    clocked_in_employees = Employee.query.join(TimeLog).filter(TimeLog.clock_out_time == None, Employee.is_active==True).all()

    return render_template('manage_timelogs.html',
                           time_logs=time_logs, employees=active_employees,
                           selected_date_str=selected_date_obj.strftime('%Y-%m-%d'),
                           selected_employee_id=selected_employee_id_int,
                           clocked_in_employees=clocked_in_employees)


@bp.route('/reports')
def reports():
    report_type = request.args.get('type', 'weekly_hours_summary')
    today = date.today()
    date_from_str = request.args.get('date_from', (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d'))
    date_to_str = request.args.get('date_to', (datetime.strptime(date_from_str, '%Y-%m-%d') + timedelta(days=6)).strftime('%Y-%m-%d'))

    try:
        date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
        date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Formato data non valido per il report.", "warning")
        date_from = today - timedelta(days=today.weekday())
        date_to = date_from + timedelta(days=6)

    report_data = []
    if report_type == 'weekly_hours_summary':
        employees = Employee.query.filter_by(is_active=True).all()
        for emp in employees:
            logs_in_range = TimeLog.query.filter(
                TimeLog.employee_id == emp.id,
                TimeLog.clock_in_time >= datetime.combine(date_from, time.min),
                TimeLog.clock_in_time <= datetime.combine(date_to, time.max),
                TimeLog.clock_out_time != None
            ).all()
            total_hours = sum(log.worked_hours for log in logs_in_range)
            report_data.append({
                'employee_id': emp.id, 'employee_name': emp.full_name,
                'total_hours': round(total_hours, 2), 'logs_count': len(logs_in_range)
            })

    return render_template('reports.html',
                           report_data=report_data, report_type=report_type,
                           date_from_str=date_from.strftime('%Y-%m-%d'),
                           date_to_str=date_to.strftime('%Y-%m-%d'))


@bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        flash('Impostazioni salvate (funzionalità non ancora implementata).', 'info')
        return redirect(url_for('main.settings'))

    flask_v = flask.__version__
    python_v = sys.version.split(" ")[0]
    db_engine_name = "N/D"
    if hasattr(db, 'engine') and db.engine:
        db_url = db.engine.url
        db_engine_name = db_url.drivername
        if db_engine_name == 'sqlite' and db_url.database:
            db_engine_name += f" ({os.path.basename(db_url.database)})"
        elif db_url.host and db_url.database: # Per DB come PostgreSQL, MySQL
            db_engine_name += f" ({db_url.host}/{db_url.database})"
        elif db_url.database: # Fallback se solo database è presente
             db_engine_name += f" ({db_url.database})"

    return render_template('settings.html',
                           flask_version=flask_v,
                           python_version=python_v,
                           db_engine=db_engine_name)


@bp.route('/api/shifts/<string:date_str>')
def api_shifts_for_day(date_str):
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        shifts = Shift.query.filter_by(shift_date=target_date).join(Employee).order_by(Shift.start_time, Employee.last_name).all()
        return jsonify([{
            'id': shift.id,
            'title': f"{shift.employee.first_name[0]}. {shift.employee.last_name} ({shift.start_time.strftime('%H:%M')}-{shift.end_time.strftime('%H:%M')})",
            'start': datetime.combine(shift.shift_date, shift.start_time).isoformat(),
            'end': datetime.combine(shift.shift_date, shift.end_time).isoformat(),
            'employee_id': shift.employee_id,
            'employee_name': shift.employee.full_name,
            'notes': shift.notes,
            'edit_url': url_for('main.edit_shift', shift_id=shift.id)
        } for shift in shifts])
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400
    except Exception as e:
        current_app.logger.error(f"API error for /api/shifts/{date_str}: {e}")
        return jsonify({'error': 'Server error'}), 500
