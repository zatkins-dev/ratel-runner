from pathlib import Path
import subprocess
import urllib
import urllib.parse

from .. import config


class Repository:
    """Class representing a repository."""

    def __init__(self, uri: str):
        self.name: str = uri.split('/')[-1].split('.')[0]
        self.uri: str = uri
        if self.uri.startswith('git@'):
            self.uri_end: str = self.uri.split(':')[-1]
        else:
            self.uri_end: str = urllib.parse.urlsplit(self.uri).path[1:].removesuffix('.git')
        self.config_key: str = f'{self.name.upper()}_DIR'
        dir = config.get_fallback(self.config_key, "")
        if dir == "":
            base_path = Path(config.get_fallback('SCRATCH_DIR')).resolve() / 'build'
            if not base_path.exists():
                base_path.mkdir(parents=True)
            self.dir = base_path / self.name
        else:
            self.dir = Path(dir).resolve()

    def __str__(self):
        return f"Repository(name={self.name}, uri={self.uri}, uri_end={self.uri_end}, config_key={self.config_key}, dir={self.dir})"

    def is_up_to_date(self):
        """Check if the repository is up to date."""
        try:
            subprocess.run(['git', 'fetch'], cwd=self.dir, check=True)
            result = subprocess.run(['git', 'status'], cwd=self.dir, check=True, capture_output=True)
            return "Your branch is up to date" in result.stdout.decode()
        except subprocess.CalledProcessError:
            return False

    def is_cloned(self):
        """Check if the repository is cloned."""
        if not self.dir.exists() or not (self.dir / '.git').exists():
            return False
        result = subprocess.run(['git', 'remote', 'show', 'origin'], cwd=self.dir, check=True, capture_output=True)
        if result.returncode != 0:
            return False
        result = result.stdout.decode()
        return self.uri_end in result

    def clone(self):
        """Clone the repository."""
        subprocess.run(['git', 'clone', self.uri, f"{self.dir}"], check=True)

    def pull(self, branch='main'):
        """Pull the latest changes from the repository."""
        subprocess.run(['git', 'fetch'], cwd=self.dir, check=True)
        subprocess.run(['git', 'checkout', branch], cwd=self.dir, check=True)
        subprocess.run(['git', 'reset', '--hard', f'origin/{branch}'], cwd=self.dir, check=True)
