from distutils.core import setup

setup(
    name='vm5k',
    version='0.1.0',
    author='Laurent Pouilloux',
    author_email='laurent.pouilloux@inria.fr',
    package_dir = {'': 'src'},
    packages=['vmutils', 'vmutils.engines', 'vmutils.services'],
    scripts=['bin/vm5k'],
    url='https://github.com/lpouillo/vm5k',
    license='LICENSE.txt',
    description='A module that helps you to deploy virtual machines on Grid5000',
    long_description=open('README.txt').read(),
)

