from distutils.core import setup

setup(
    name='vm5k',
    version='0.6.2',
    author='Laurent Pouilloux',
    author_email='laurent.pouilloux@inria.fr',
    package_dir={'': 'src'},
    packages=['vm5k', 'vm5k.services'],
    scripts=['bin/vm5k', 'bin/vm5k_topology'],
    url='https://github.com/lpouillo/vm5k',
    license='LICENSE.txt',
    description='A python module to ease the experimentations ' + \
        'of virtual Machines on the Grid\'5000 platform.',
    long_description=open('README.txt').read(),
)
