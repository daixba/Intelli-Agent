/**********************************************************************************************************************
 *  Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.                                                *
 *                                                                                                                    *
 *  Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance    *
 *  with the License. A copy of the License is located at                                                             *
 *                                                                                                                    *
 *      http://www.apache.org/licenses/LICENSE-2.0                                                                    *
 *                                                                                                                    *
 *  or in the 'license' file accompanying this file. This file is distributed on an 'AS IS' BASIS, WITHOUT WARRANTIES *
 *  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    *
 *  and limitations under the License.                                                                                *
 *********************************************************************************************************************/

import { Aws, Duration, StackProps } from "aws-cdk-lib";
import * as apigw from "aws-cdk-lib/aws-apigateway";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambdaEventSources from "aws-cdk-lib/aws-lambda-event-sources";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3n from "aws-cdk-lib/aws-s3-notifications";
import * as sfn from "aws-cdk-lib/aws-stepfunctions";
import { Construct } from "constructs";
import { join } from "path";

import { BuildConfig } from "../../lib/shared/build-config";
import { Constants } from "../shared/constants";
import { LambdaLayers } from "../shared/lambda-layers";
import { QueueConstruct } from "./api-queue";
import { WebSocketConstruct } from "./websocket-api";
import { Function, Runtime, Code, Architecture, DockerImageFunction, DockerImageCode } from 'aws-cdk-lib/aws-lambda';
import { UserPool } from "aws-cdk-lib/aws-cognito";
import { IAMHelper } from "../shared/iam-helper";
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { JsonSchemaType, JsonSchemaVersion, Model } from "aws-cdk-lib/aws-apigateway";


interface ApiStackProps extends StackProps {
  domainEndpoint: string;
  embeddingAndRerankerEndPoint: string;
  llmModelId: string;
  instructEndPoint: string;
  sessionsTableName: string;
  messagesTableName: string;
  botTableName: string;
  userPool: UserPool;
  userPoolClientId: string;
  iamHelper: IAMHelper;
}

export class ApiConstruct extends Construct {
  public apiEndpoint: string = "";
  public wsEndpoint: string = "";
  public wsEndpointV2: string = "";
  private iamHelper: IAMHelper;

  constructor(scope: Construct, id: string, props: ApiStackProps) {
    super(scope, id);

    this.iamHelper = props.iamHelper;
    const domainEndpoint = props.domainEndpoint;
    const sessionsTableName = props.sessionsTableName;
    const messagesTableName = props.messagesTableName;
    const botTableName = props.botTableName;

    const queueConstruct = new QueueConstruct(this, "LLMQueueStack", {
      namePrefix: Constants.API_QUEUE_NAME,
    });
    const sqsStatement = queueConstruct.sqsStatement;
    const messageQueue = queueConstruct.messageQueue;
    const messageQueueV2 = queueConstruct.messageQueue;

    const lambdaLayers = new LambdaLayers(this);
    // const apiLambdaExecutorLayer = lambdaLayers.createExecutorLayer();
    const apiLambdaEmbeddingLayer = lambdaLayers.createEmbeddingLayer();
    const apiLambdaOnlineSourceLayer = lambdaLayers.createOnlineSourceLayer();
    const apiLambdaJobSourceLayer = lambdaLayers.createJobSourceLayer();
    const apiLambdaAuthorizerLayer = lambdaLayers.createAuthorizerLayer();

    const embeddingLambda = new Function(this, "lambdaEmbedding", {
      runtime: Runtime.PYTHON_3_12,
      handler: "main.lambda_handler",
      code: Code.fromAsset(join(__dirname, "../../../lambda/embedding")),
      timeout: Duration.minutes(15),
      memorySize: 4096,
      // vpc: apiVpc,
      // vpcSubnets: {
      //   subnets: apiVpc.privateSubnets,
      // },
      // securityGroups: [securityGroup],
      architecture: Architecture.X86_64,
      environment: {
        REGION: Aws.REGION,
      },
      layers: [apiLambdaEmbeddingLayer],
    });

    embeddingLambda.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "es:ESHttpGet",
          "es:ESHttpPut",
          "es:ESHttpPost",
          "es:ESHttpHead",
        ],
        effect: iam.Effect.ALLOW,
        resources: ["*"],
      }),
    );
    embeddingLambda.addToRolePolicy(this.iamHelper.s3Statement);
    embeddingLambda.addToRolePolicy(this.iamHelper.endpointStatement);


    // Create Lambda Authorizer for WebSocket API
    const customAuthorizerLambda = new Function(this, "CustomAuthorizerLambda", {
      runtime: Runtime.PYTHON_3_12,
      handler: "custom_authorizer.lambda_handler",
      code: Code.fromAsset(join(__dirname, "../../../lambda/authorizer")),
      timeout: Duration.minutes(15),
      memorySize: 1024,
      // vpc: apiVpc,
      // vpcSubnets: {
      //   subnets: apiVpc.privateSubnets,
      // },
      // securityGroups: [securityGroup],
      architecture: Architecture.X86_64,
      environment: {
        USER_POOL_ID: props.userPool.userPoolId,
        REGION: Aws.REGION,
        APP_CLIENT_ID: props.userPoolClientId,
      },
      layers: [apiLambdaAuthorizerLayer],
    });

    customAuthorizerLambda.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        effect: iam.Effect.ALLOW,
        resources: ["*"],
      }),
    );

    // const listWorkspaceLambda = new Function(this, "ListWorkspaceLambda", {
    //   code: Code.fromAsset(join(__dirname, "../../../lambda/etl")),
    //   handler: "list_workspace.lambda_handler",
    //   runtime: Runtime.PYTHON_3_12,
    //   timeout: Duration.minutes(15),
    //   memorySize: 512,
    //   architecture: Architecture.X86_64,
    //   environment: {
    //     USER_POOL_ID: props.userPool.userPoolId,
    //   },
    // });
    //
    // listWorkspaceLambda.addToRolePolicy(this.iamHelper.cognitoStatement);


    // Define the API Gateway
    const api = new apigw.RestApi(this, `${Constants.SOLUTION_SHORT_NAME.toLowerCase()}-api`, {
      // restApiName: `${Constants.SOLUTION_SHORT_NAME.toLowerCase()}-api`,
      description: `${Constants.SOLUTION_NAME} - Core API`,
      endpointConfiguration: {
        types: [apigw.EndpointType.REGIONAL],
      },
      defaultCorsPreflightOptions: {
        allowHeaders: [
          "Content-Type",
          "X-Amz-Date",
          "Authorization",
          "X-Api-Key",
          "X-Amz-Security-Token",
        ],
        allowMethods: apigw.Cors.ALL_METHODS,
        allowCredentials: true,
        allowOrigins: apigw.Cors.ALL_ORIGINS,
      },
      deployOptions: {
        stageName: "prod",
        metricsEnabled: true,
        loggingLevel: apigw.MethodLoggingLevel.INFO,
        dataTraceEnabled: true,
        tracingEnabled: true,
      },
    });

    const auth = new apigw.RequestAuthorizer(this, 'ApiAuthorizer', {
      handler: customAuthorizerLambda,
      identitySources: [apigw.IdentitySource.header('Authorization')],
    });

    // Define the API Gateway Lambda Integration with proxy and no integration responses
    const lambdaEmbeddingIntegration = new apigw.LambdaIntegration(
      embeddingLambda,
      { proxy: true },
    );

    const responseModel = new Model(this, 'ResponseModel', {
      restApi: api,
      schema: {
        schema: JsonSchemaVersion.DRAFT4,
        title: 'ResponsePayload',
        type: JsonSchemaType.OBJECT,
        properties: {
          data: { type: JsonSchemaType.STRING },
          message: { type: JsonSchemaType.STRING }
        },
      },
    });

    const methodOption = {
      authorizer: auth,
      methodResponses: [
        {
          statusCode: '200',
          responseModels: {
            'application/json': responseModel,
          }
        },
        {
          statusCode: '400',
          responseModels: {
            'application/json': apigw.Model.EMPTY_MODEL,
          },
        },
        {
          statusCode: '500',
          responseModels: {
            'application/json': apigw.Model.EMPTY_MODEL,
          },
        }
      ]
    };

    // Define the API Gateway Method
    const apiResourceEmbedding = api.root.addResource("v1");
    // apiResourceEmbedding.addMethod("{proxy+}", lambdaEmbeddingIntegration, methodOption);
    apiResourceEmbedding.addProxy({
      defaultIntegration: lambdaEmbeddingIntegration,
      defaultMethodOptions: methodOption,
    })


    const lambdaOnlineMain = new Function(this, "lambdaOnlineMain", {
      runtime: Runtime.PYTHON_3_12,
      handler: "main.lambda_handler",
      code: Code.fromAsset(
        join(__dirname, "../../../lambda/online/lambda_main"),
      ),
      timeout: Duration.minutes(15),
      memorySize: 4096,
      // vpc: apiVpc,
      // vpcSubnets: {
      //   subnets: apiVpc.privateSubnets,
      // },
      // securityGroups: [securityGroup],
      architecture: Architecture.X86_64,
      layers: [apiLambdaOnlineSourceLayer, apiLambdaJobSourceLayer],
      environment: {
        aos_endpoint: domainEndpoint,
        rerank_endpoint: props.embeddingAndRerankerEndPoint,
        sessions_table_name: sessionsTableName,
        messages_table_name: messagesTableName,
        workspace_table: botTableName,
        // openai_key_arn: openAiKey.secretArn,
      },
    });

    lambdaOnlineMain.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "es:ESHttpGet",
          "es:ESHttpPut",
          "es:ESHttpPost",
          "es:ESHttpHead",
          "secretsmanager:GetSecretValue",
          "bedrock:*",
          "lambda:InvokeFunction",
        ],
        effect: iam.Effect.ALLOW,
        resources: ["*"],
      }),
    );
    lambdaOnlineMain.addToRolePolicy(sqsStatement);
    lambdaOnlineMain.addEventSource(
      new lambdaEventSources.SqsEventSource(messageQueue, { batchSize: 1 }),
    );
    lambdaOnlineMain.addToRolePolicy(this.iamHelper.s3Statement);
    lambdaOnlineMain.addToRolePolicy(this.iamHelper.endpointStatement);
    lambdaOnlineMain.addToRolePolicy(this.iamHelper.dynamodbStatement);



    // Define the API Gateway Lambda Integration with proxy and no integration responses
    const lambdaExecutorIntegration = new apigw.LambdaIntegration(
      lambdaOnlineMain,
      { proxy: true },
    );

    // Define the API Gateway Method
    const apiResourceLLM = api.root.addResource("llm");
    apiResourceLLM.addMethod("POST", lambdaExecutorIntegration, methodOption);

    const lambdaDispatcher = new Function(this, "lambdaDispatcher", {
      runtime: Runtime.PYTHON_3_12,
      handler: "main.lambda_handler",
      code: Code.fromAsset(join(__dirname, "../../../lambda/dispatcher")),
      timeout: Duration.minutes(15),
      memorySize: 1024,
      // vpc: apiVpc,
      // vpcSubnets: {
      //   subnets: apiVpc.privateSubnets,
      // },
      // securityGroups: [securityGroup],
      architecture: Architecture.X86_64,
      environment: {
        SQS_QUEUE_URL: messageQueue.queueUrl,
      },
    });
    lambdaDispatcher.addToRolePolicy(sqsStatement);

    const webSocketApi = new WebSocketConstruct(this, "WebSocketApi", {
      dispatcherLambda: lambdaDispatcher,
      sendMessageLambda: lambdaOnlineMain,
      customAuthorizerLambda: customAuthorizerLambda,
    });
    let wsStage = webSocketApi.websocketApiStage
    this.wsEndpoint = `${wsStage.api.apiEndpoint}/${wsStage.stageName}/`;

    this.apiEndpoint = api.url;
  }
}
