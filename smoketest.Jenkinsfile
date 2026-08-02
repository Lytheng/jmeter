pipeline {
    agent any

    environment {
        SMOKE_TEST_DIR = "jmeter"
        DOCKER_WORK_DIR     = "/regression-test/scripts"
    }

    stages {
        stage('Build') {
            steps {
                echo 'Building the application...'
            }
        }
        stage('Test') {
            steps {
                echo 'Testing the application...'
                script {
                    // make runlocal.py executable (Only for script used in custom docker --entrypoint)
                    sh 'chmod o+x scripts/runlocal.py'
                }
            }
        }
        stage('Deploy') {
            steps {
                echo 'Deploying the application...'
            }
        }
    }
    
    post {
        always {
            cleanWs()
        }
    }
}
