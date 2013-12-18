from distutils.core import setup

setup(
    name='vm5k',
    version='0.1.0',
    author='Laurent Pouilloux',
    author_email='laurent.pouilloux@inria.fr',
    packages=['vm5k', 'vm5k.engines', 'vm5k.services'],
    scripts=['vm5k'],
    url='https://github.com/lpouillo/vm5k',
    license='LICENSE.txt',
    description='A module that helps you to ',
    long_description=open('README.txt').read(),
    install_requires=[
        "execo >= 2.2",
        "matplotlib >= 1.2.1",
    ],
)

