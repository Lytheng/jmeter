pipeline {
    agent any

    environment {
        SMOKE_TEST_DIR = "CICD_SMOKE_TEST"
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
                    sh 'chmod o+x ${SMOKE_TEST_DIR}/scripts/runlocal.py'
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
