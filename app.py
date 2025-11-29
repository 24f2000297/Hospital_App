from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Patient, Doctor, Department, Appointment, MedicalRecord
from forms import LoginForm, RegistrationForm, AppointmentForm
from datetime import datetime, timedelta
import os

app = Flask(__name__)
# Use environment variables for production, fallback to defaults for local dev
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///hospital_management.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Initialize database
with app.app_context():
    db.create_all()
    # Create admin user if it doesn't exist
    admin_email = 'admin@hospital.com'
    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        admin_user = User(
            username='admin',
            email=admin_email,
            password=generate_password_hash('admin123'),
            role='admin'
        )
        db.session.add(admin_user)
        try:
            db.session.commit()
            print("Admin user created successfully!")
        except Exception as e:
            db.session.rollback()
            print(f"Error creating admin user: {e}")
    else:
        print("Admin user already exists.")

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            password=generate_password_hash(form.password.data),
            role='patient'  # Default role is patient
        )
        db.session.add(user)
        try:
            db.session.commit()
            # Create a patient record
            patient = Patient(
                user_id=user.id,
                name=form.username.data,  # Using username as name initially
                dob=datetime.now(),  # Default date, should be updated later
                gender='Not specified',  # Default gender
                phone='Not specified'  # Default phone
            )
            db.session.add(patient)
            db.session.commit()
            flash('Registration successful! Please login and complete your profile.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Registration failed. Please try again.', 'danger')
            return redirect(url_for('register'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        print(f"Login attempt - Email: {form.email.data}, Role: {form.role.data}")  # Debug print
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            print(f"User found - Role: {user.role}")  # Debug print
            if check_password_hash(user.password, form.password.data):
                if user.role == form.role.data or (user.role == 'admin' and form.role.data == 'admin'):
                    session['user_id'] = user.id
                    session['role'] = user.role
                    flash('Login successful!', 'success')
                    print(f"Login successful - Redirecting to {user.role} dashboard")  # Debug print
                    if user.role == 'patient':
                        return redirect(url_for('patient_dashboard'))
                    elif user.role == 'doctor':
                        return redirect(url_for('doctor_dashboard'))
                    elif user.role == 'admin':
                        return redirect(url_for('admin_dashboard'))
                else:
                    flash(f'Invalid role selected. You are registered as a {user.role}.', 'danger')
            else:
                flash('Invalid password.', 'danger')
        else:
            flash('Email not found.', 'danger')
    return render_template('login.html', form=form)

@app.route('/patient_dashboard')
def patient_dashboard():
    if 'user_id' not in session or session['role'] != 'patient':
        return redirect(url_for('login'))
    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    
    if not patient:
        flash('Patient profile not found. Please complete your registration.', 'danger')
        return redirect(url_for('logout'))
    
    # Get patient's appointments
    total_appointments = Appointment.query.filter_by(patient_id=patient.id).all()
    
    # Get upcoming/scheduled appointments (sorted by date and time)
    upcoming_appointments = Appointment.query.filter_by(
        patient_id=patient.id,
        status='Scheduled'
    ).filter(
        Appointment.appointment_date >= datetime.now().date()
    ).order_by(
        Appointment.appointment_date.asc(),
        Appointment.time_slot.asc()
    ).all()
    
    # Get completed appointments (sorted by date descending)
    completed_appointments = Appointment.query.filter_by(
        patient_id=patient.id,
        status='Completed'
    ).order_by(
        Appointment.appointment_date.desc(),
        Appointment.time_slot.desc()
    ).all()
    
    # Get medical reports
    medical_records = MedicalRecord.query.filter_by(patient_id=patient.id).count()
    
    return render_template('patient_dashboard.html', 
                         patient=patient,
                         total_appointments=total_appointments,
                         upcoming_appointments=upcoming_appointments,
                         completed_appointments=completed_appointments,
                         medical_records=medical_records)

@app.route('/doctor_dashboard')
def doctor_dashboard():
    if 'user_id' not in session or session['role'] != 'doctor':
        return redirect(url_for('login'))
    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    
    # Get today's appointments
    today = datetime.now().date()
    today_appointments = Appointment.query.filter_by(doctor_id=doctor.id).filter(
        Appointment.appointment_date == today
    ).order_by(Appointment.time_slot.asc()).all()
    
    # Get upcoming appointments (excluding today)
    upcoming_appointments = Appointment.query.filter_by(doctor_id=doctor.id).filter(
        Appointment.appointment_date > today
    ).order_by(Appointment.appointment_date.asc()).all()
    
    return render_template('doctor_dashboard.html', 
                         doctor=doctor,
                         today_appointments=today_appointments,
                         upcoming_appointments=upcoming_appointments)

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session or session['role'] != 'doctor':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate inputs
        if not all([current_password, new_password, confirm_password]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('change_password'))
        
        # Check if new passwords match
        if new_password != confirm_password:
            flash('New passwords do not match!', 'danger')
            return redirect(url_for('change_password'))
        
        # Check password length
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long!', 'danger')
            return redirect(url_for('change_password'))
        
        # Get user and verify current password
        user = User.query.get(session['user_id'])
        if not check_password_hash(user.password, current_password):
            flash('Current password is incorrect!', 'danger')
            return redirect(url_for('change_password'))
        
        try:
            # Update password
            user.password = generate_password_hash(new_password)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('doctor_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error changing password: {str(e)}', 'danger')
            return redirect(url_for('change_password'))
    
    return render_template('change_password.html')

@app.route('/update_patient_profile', methods=['GET', 'POST'])
def update_patient_profile():
    if 'user_id' not in session or session['role'] != 'patient':
        return redirect(url_for('login'))
    
    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        flash('Patient profile not found.', 'danger')
        return redirect(url_for('logout'))
    
    if request.method == 'POST':
        gender = request.form.get('gender')
        phone = request.form.get('phone')
        address = request.form.get('address')
        
        if not gender or not phone:
            flash('Gender and phone number are required!', 'danger')
            return redirect(url_for('update_patient_profile'))
        
        try:
            patient.gender = gender
            patient.phone = phone
            patient.address = address if address else patient.address
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('patient_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'danger')
    
    return render_template('update_patient_profile.html', patient=patient)

@app.route('/update_doctor_profile', methods=['GET', 'POST'])
def update_doctor_profile():
    if 'user_id' not in session or session['role'] != 'doctor':
        return redirect(url_for('login'))
    
    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        flash('Doctor profile not found.', 'danger')
        return redirect(url_for('logout'))
    
    if request.method == 'POST':
        gender = request.form.get('gender')
        phone = request.form.get('phone')
        
        if not gender or not phone:
            flash('Gender and phone number are required!', 'danger')
            return redirect(url_for('update_doctor_profile'))
        
        try:
            doctor.gender = gender
            doctor.phone = phone
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('doctor_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'danger')
    
    return render_template('update_doctor_profile.html', doctor=doctor)

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    # Fetch statistics for the dashboard
    departments = Department.query.all()
    doctors = Doctor.query.all()
    patients = Patient.query.all()
    appointments = Appointment.query.order_by(Appointment.appointment_date.desc()).all()
    
    return render_template('admin_dashboard.html',
                         departments=departments,
                         doctors=doctors,
                         patients=patients,
                         appointments=appointments)

@app.route('/book_appointment', methods=['GET', 'POST'])
def book_appointment():
    if 'user_id' not in session or session['role'] != 'patient':
        return redirect(url_for('login'))
    
    form = AppointmentForm()
    if request.method == 'POST':
        doctor_id = request.form.get('doctor_id')
        appointment_date = datetime.strptime(request.form.get('appointment_date'), '%Y-%m-%d').date()
        time_slot = request.form.get('time_slot')
        
        # Determine period based on time
        hour = int(time_slot.split(':')[0])
        if 6 <= hour < 12:
            period = 'Morning'
        elif 12 <= hour < 17:
            period = 'Afternoon'
        else:
            period = 'Evening'
        
        # Check if slot is still available
        existing_appointment = Appointment.query.filter_by(
            doctor_id=doctor_id,
            appointment_date=appointment_date,
            time_slot=time_slot
        ).first()
        
        if existing_appointment:
            flash('Sorry, this time slot is no longer available. Please choose another.', 'danger')
        else:
            patient = Patient.query.filter_by(user_id=session['user_id']).first()
            appointment = Appointment(
                patient_id=patient.id,
                doctor_id=doctor_id,
                appointment_date=appointment_date,
                time_slot=time_slot,
                period=period
            )
            db.session.add(appointment)
            try:
                db.session.commit()
                flash('Appointment booked successfully!', 'success')
                return redirect(url_for('patient_dashboard'))
            except Exception as e:
                db.session.rollback()
                flash('Error booking appointment. Please try again.', 'danger')
    
    doctors = Doctor.query.all()
    min_date = datetime.now().date().strftime('%Y-%m-%d')
    max_date = (datetime.now().date() + timedelta(days=7)).strftime('%Y-%m-%d')
    
    return render_template('book_appointment.html', 
                         form=form, 
                         doctors=doctors,
                         min_date=min_date,
                         max_date=max_date)

@app.route('/get_available_slots/<int:doctor_id>/<date>')
def get_available_slots(doctor_id, date):
    if 'user_id' not in session or session['role'] != 'patient':
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Convert date string to date object
    appointment_date = datetime.strptime(date, '%Y-%m-%d').date()
    
    # Define all possible time slots for each period
    time_slots = {
        'morning': ['09:00', '09:30', '10:00', '10:30', '11:00', '11:30'],
        'afternoon': ['13:00', '13:30', '14:00', '14:30', '15:00', '15:30', '16:00', '16:30'],
        'evening': ['17:00', '17:30', '18:00', '18:30', '19:00', '19:30']
    }
    
    # If the date is today, remove past time slots
    if appointment_date == datetime.now().date():
        current_time = datetime.now().time()
        for period in time_slots:
            time_slots[period] = [
                slot for slot in time_slots[period] 
                if datetime.strptime(slot, '%H:%M').time() > current_time
            ]
    
    # Get booked appointments for this doctor on this date
    booked_appointments = Appointment.query.filter_by(
        doctor_id=doctor_id,
        appointment_date=appointment_date
    ).all()
    
    # Create set of booked time slots
    booked_slots = {appt.time_slot for appt in booked_appointments}
    
    # Remove booked slots from available slots
    available_slots = {
        'morning': [slot for slot in time_slots['morning'] if slot not in booked_slots],
        'afternoon': [slot for slot in time_slots['afternoon'] if slot not in booked_slots],
        'evening': [slot for slot in time_slots['evening'] if slot not in booked_slots]
    }
    
    return jsonify(available_slots)

@app.route('/view_appointments')
def view_appointments():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        flash('Patient profile not found.', 'danger')
        return redirect(url_for('patient_dashboard'))
    
    # Get scheduled appointments sorted by date and time
    scheduled_appointments = Appointment.query.filter_by(
        patient_id=patient.id,
        status='Scheduled'
    ).order_by(
        Appointment.appointment_date.asc(),
        Appointment.time_slot.asc()
    ).all()
    
    # Get completed appointments sorted by date descending
    completed_appointments = Appointment.query.filter_by(
        patient_id=patient.id,
        status='Completed'
    ).order_by(
        Appointment.appointment_date.desc(),
        Appointment.time_slot.desc()
    ).all()
    
    return render_template('view_appointments.html', 
                         scheduled_appointments=scheduled_appointments,
                         completed_appointments=completed_appointments)

@app.route('/view_medical_records')
def view_medical_records():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    records = MedicalRecord.query.filter_by(patient_id=patient.id).all()
    return render_template('view_medical_records.html', records=records)

@app.route('/doctor_appointments')
def doctor_appointments():
    if 'user_id' not in session or session['role'] != 'doctor':
        return redirect(url_for('login'))
    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        flash('Doctor profile not found.', 'danger')
        return redirect(url_for('login'))
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).order_by(Appointment.appointment_date).all()
    return render_template('doctor_appointments.html', appointments=appointments, doctor=doctor)

@app.route('/doctor_patients')
def doctor_patients():
    if 'user_id' not in session or session['role'] != 'doctor':
        return redirect(url_for('login'))
    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        flash('Doctor profile not found.', 'danger')
        return redirect(url_for('login'))
    # Get unique patients from appointments
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()
    patients = list(set([appt.patient for appt in appointments]))
    return render_template('doctor_patients.html', patients=patients, doctor=doctor)

@app.route('/complete_appointment/<int:id>', methods=['POST'])
def complete_appointment(id):
    if 'user_id' not in session or session['role'] != 'doctor':
        return redirect(url_for('login'))
    
    try:
        appointment = Appointment.query.get_or_404(id)
        
        # Verify this appointment belongs to the logged-in doctor
        doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
        if appointment.doctor_id != doctor.id:
            flash('You can only complete your own appointments!', 'danger')
            return redirect(url_for('doctor_appointments'))
        
        # Update status to Completed
        appointment.status = 'Completed'
        db.session.commit()
        flash('Appointment marked as completed!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error completing appointment: {str(e)}', 'danger')
    
    return redirect(url_for('doctor_appointments'))

@app.route('/add_medical_record/<int:appointment_id>', methods=['GET', 'POST'])
def add_medical_record(appointment_id):
    if 'user_id' not in session or session['role'] != 'doctor':
        return redirect(url_for('login'))
    
    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Verify this appointment belongs to the logged-in doctor
    if appointment.doctor_id != doctor.id:
        flash('You can only add records for your own appointments!', 'danger')
        return redirect(url_for('doctor_appointments'))
    
    # Check if report already exists
    existing_record = MedicalRecord.query.filter_by(appointment_id=appointment_id).first()
    if existing_record:
        flash('Medical report already exists for this appointment!', 'warning')
        return redirect(url_for('view_medical_record', appointment_id=appointment_id))
    
    if request.method == 'POST':
        diagnosis = request.form.get('diagnosis')
        prescription = request.form.get('prescription')
        notes = request.form.get('notes')
        
        if not diagnosis or not prescription:
            flash('Diagnosis and prescription are required!', 'danger')
            return redirect(url_for('add_medical_record', appointment_id=appointment_id))
        
        try:
            # Create medical report
            record = MedicalRecord(
                patient_id=appointment.patient_id,
                appointment_id=appointment_id,
                diagnosis=diagnosis,
                prescription=prescription,
                notes=notes
            )
            db.session.add(record)
            
            # Update appointment status to Completed
            appointment.status = 'Completed'
            
            db.session.commit()
            flash('Medical report added successfully!', 'success')
            return redirect(url_for('doctor_appointments'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding medical report: {str(e)}', 'danger')
    
    return render_template('add_medical_record.html', appointment=appointment, doctor=doctor)

@app.route('/view_medical_record/<int:appointment_id>')
def view_medical_record(appointment_id):
    if 'user_id' not in session or session['role'] != 'doctor':
        return redirect(url_for('login'))
    
    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Verify this appointment belongs to the logged-in doctor
    if appointment.doctor_id != doctor.id:
        flash('You can only view records for your own appointments!', 'danger')
        return redirect(url_for('doctor_appointments'))
    
    record = MedicalRecord.query.filter_by(appointment_id=appointment_id).first()
    if not record:
        flash('No medical report found for this appointment!', 'warning')
        return redirect(url_for('doctor_appointments'))
    
    return render_template('view_medical_record_doctor.html', record=record, appointment=appointment, doctor=doctor)

@app.route('/doctor_medical_records')
def doctor_medical_records():
    if 'user_id' not in session or session['role'] != 'doctor':
        return redirect(url_for('login'))
    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        flash('Doctor profile not found.', 'danger')
        return redirect(url_for('login'))
    # Get all appointments for this doctor
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()
    appointment_ids = [appt.id for appt in appointments]
    records = MedicalRecord.query.filter(MedicalRecord.appointment_id.in_(appointment_ids)).all()
    return render_template('doctor_medical_records.html', records=records, doctor=doctor)

@app.route('/manage_doctors', methods=['GET', 'POST'])
def manage_doctors():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    # Show form to add doctor and list existing doctors
    departments = Department.query.all()
    if request.method == 'POST':
        # Add new doctor (create a User + Doctor)
        name = request.form.get('name')
        email = request.form.get('email')
        specialization = request.form.get('specialization')
        department_id = request.form.get('department_id')
        fees = request.form.get('fees', 500.0)  # Default to 500 if not provided
        if not (name and email and department_id):
            flash('Please provide name, email and department.', 'danger')
            return redirect(url_for('manage_doctors'))

        # Check if user/email exists
        if User.query.filter_by(email=email).first():
            flash('A user with that email already exists.', 'danger')
            return redirect(url_for('manage_doctors'))

        try:
            # create user with default password 'doctor123'
            user = User(username=name, email=email, password=generate_password_hash('doctor123'), role='doctor')
            db.session.add(user)
            db.session.flush()
            doctor = Doctor(user_id=user.id, name=name, specialization=specialization or 'General', 
                          department_id=int(department_id), fees=float(fees))
            db.session.add(doctor)
            db.session.commit()
            flash(f'Doctor "{name}" added successfully. Temporary password is "doctor123"', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding doctor: {e}', 'danger')
        return redirect(url_for('manage_doctors'))

    doctors = Doctor.query.all()
    return render_template('manage_doctors.html', doctors=doctors, departments=departments)

@app.route('/manage_patients')
def manage_patients():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    patients = Patient.query.all()
    return render_template('manage_patients.html', patients=patients)

@app.route('/delete_patient/<int:id>', methods=['POST'])
def delete_patient(id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    try:
        patient = Patient.query.get_or_404(id)
        
        # Delete associated records first
        Appointment.query.filter_by(patient_id=id).delete()
        MedicalRecord.query.filter_by(patient_id=id).delete()
        
        # Delete associated user account if exists
        if patient.user_id:
            user = User.query.get(patient.user_id)
            if user:
                db.session.delete(user)
        
        # Delete patient
        db.session.delete(patient)
        db.session.commit()
        flash('Patient and all associated records deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting patient: {str(e)}', 'danger')
    
    return redirect(url_for('manage_patients'))

@app.route('/manage_departments', methods=['GET', 'POST'])
def manage_departments():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            department = Department(name=name)
            db.session.add(department)
            try:
                db.session.commit()
                flash('Department added successfully!', 'success')
            except:
                db.session.rollback()
                flash('Error adding department.', 'danger')
        return redirect(url_for('manage_departments'))
    
    departments = Department.query.all()
    return render_template('manage_departments.html', departments=departments)

@app.route('/edit_department/<int:id>', methods=['POST'])
def edit_department(id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    department = Department.query.get_or_404(id)
    name = request.form.get('name')
    if name:
        department.name = name
        try:
            db.session.commit()
            flash('Department updated successfully!', 'success')
        except:
            db.session.rollback()
            flash('Error updating department.', 'danger')
    return redirect(url_for('manage_departments'))

@app.route('/delete_department/<int:id>', methods=['POST'])
def delete_department(id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    department = Department.query.get_or_404(id)
    if department.doctors:
        flash('Cannot delete department with assigned doctors.', 'danger')
    else:
        try:
            db.session.delete(department)
            db.session.commit()
            flash('Department deleted successfully!', 'success')
        except:
            db.session.rollback()
            flash('Error deleting department.', 'danger')
    return redirect(url_for('manage_departments'))

@app.route('/edit_doctor/<int:id>', methods=['POST'])
def edit_doctor(id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    doctor = Doctor.query.get_or_404(id)
    name = request.form.get('name')
    specialization = request.form.get('specialization')
    department_id = request.form.get('department_id')
    fees = request.form.get('fees')
    if name:
        doctor.name = name
    if specialization is not None:
        doctor.specialization = specialization
    if department_id:
        doctor.department_id = int(department_id)
    if fees:
        doctor.fees = float(fees)
    try:
        db.session.commit()
        flash('Doctor updated successfully!', 'success')
    except:
        db.session.rollback()
        flash('Error updating doctor.', 'danger')
    return redirect(url_for('manage_doctors'))

@app.route('/delete_doctor/<int:id>', methods=['POST'])
def delete_doctor(id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    doctor = Doctor.query.get_or_404(id)
    # Prevent deletion if doctor has appointments
    if doctor.appointments:
        flash('Cannot delete doctor with existing appointments.', 'danger')
        return redirect(url_for('manage_doctors'))
    try:
        # optionally delete associated user
        user = User.query.get(doctor.user_id)
        db.session.delete(doctor)
        if user:
            db.session.delete(user)
        db.session.commit()
        flash('Doctor deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting doctor: {e}', 'danger')
    return redirect(url_for('manage_doctors'))

@app.route('/manage_appointments')
def manage_appointments():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    appointments = Appointment.query.order_by(Appointment.appointment_date.desc()).all()
    return render_template('manage_appointments.html', appointments=appointments)

@app.route('/delete_appointment/<int:id>', methods=['POST'])
def delete_appointment(id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    appt = Appointment.query.get_or_404(id)
    try:
        db.session.delete(appt)
        db.session.commit()
        flash('Appointment deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting appointment: {e}', 'danger')
    return redirect(url_for('manage_appointments'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)