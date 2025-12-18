# PowerShell helper to create a virtual environment and install dependencies.
# Usage (PowerShell):
#   1) Open PowerShell in project root
#   2) Run: .\setup_env.ps1
#   3) To force recreate venv: .\setup_env.ps1 -Force
param(
    [switch]$Force
)

$venvDir = ".venv"
if (Test-Path $venvDir) {
    if (-not $Force) {
        Write-Host "Virtual environment already exists at '$venvDir'. Use -Force to recreate." -ForegroundColor Yellow
        Write-Host "To activate: .\$venvDir\Scripts\Activate.ps1"
        exit 0
    }
    Write-Host "Removing existing virtual environment..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venvDir
}

Write-Host "Creating virtual environment at '$venvDir'..."
python -m venv $venvDir

Write-Host "Activating virtual environment and upgrading pip..."
& "$venvDir\Scripts\Activate.ps1"
python -m pip install --upgrade pip

Write-Host "Installing requirements from requirements.txt..."
pip install -r requirements.txt

Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Activate the environment with: .\$venvDir\Scripts\Activate.ps1"
Write-Host "Run the FastAPI server: uvicorn Text2SQL_Agent:app --host 0.0.0.0 --port 8000 --reload"
