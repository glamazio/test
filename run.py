from app import create_app, db
from app.models import User, Employee, Role, StoreHours, Shift, TimeLog # Import your models

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {
        'db': db,
        'User': User,
        'Employee': Employee,
        'Role': Role,
        'StoreHours': StoreHours,
        'Shift': Shift,
        'TimeLog': TimeLog
    }

if __name__ == '__main__':
    app.run(debug=app.config['DEBUG'])
