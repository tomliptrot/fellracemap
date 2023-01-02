poetry run build
pre-commit run --files www/index.html
git add www/index.html
git commit -m "site rebuild"
git push
