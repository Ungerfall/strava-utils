using IdentityModel;
using IdentityModel.Client;
using RestSharp;
using RestSharp.Authenticators;

namespace StravaSharp.OAuth2Client;

public abstract class OAuth2Client(OAuth2ClientConfiguration config) : IAuthenticator
{
    protected DateTime TokenExpiresAtUtc { get; set; } = config.TokenExpiresAt;
    protected string AccessToken { get; set; } = config.AccessToken;
    protected string RefreshToken { get; set; } = config.RefreshToken;

    protected abstract string AuthorizeUri { get; }
    protected abstract string TokenUri { get; }

    protected OAuth2ClientConfiguration Configuration { get; } = config;

    public async ValueTask Authenticate(IRestClient client, RestRequest request)
    {
        await EnsureValidTokenAsync();
        request.AddOrUpdateParameter(new HeaderParameter(KnownHeaders.Authorization, AccessToken));
    }

    protected async Task EnsureValidTokenAsync()
    {
        bool missingOrExpired = string.IsNullOrEmpty(AccessToken)
            || (TokenExpiresAtUtc <= DateTime.UtcNow.AddSeconds(60));
        if (missingOrExpired)
        {
            await UpdateAccessToken();
        }
    }

    protected string GetAuthorizationUrl()
    {
        RestClient client = new();

        RestRequest request = new RestRequest(new Uri(AuthorizeUri))
            .AddParameter(OidcConstants.AuthorizeRequest.ClientId, Configuration.ClientId)
            .AddParameter(OidcConstants.AuthorizeRequest.RedirectUri, Configuration.RedirectUri)
            .AddParameter(OidcConstants.AuthorizeRequest.Scope, Configuration.Scope);
        CustomizeAuthorizationUrlRequest(request);
        Uri authorizationUri = BuildUriExtensions.BuildUri(client, request);
        return authorizationUri.ToString();
    }

    protected virtual void CustomizeAuthorizationUrlRequest(RestRequest request)
    {
    }

    public abstract Task Authorize(IDictionary<string, string> redirectUrlParameters);

    public virtual async Task UpdateAccessToken(string? refreshToken = null)
    {
        string refreshTokenToUse = (refreshToken ?? RefreshToken) ?? throw new InvalidOperationException("Cannot update access token without refreshtoken");
        HttpClient client = new();
        TokenResponse? response = await client.RequestRefreshTokenAsync(new RefreshTokenRequest
        {
            Address = TokenUri,
            ClientId = Configuration.ClientId,
            ClientSecret = Configuration.ClientSecret,
            GrantType = OidcConstants.TokenRequest.RefreshToken,
            RefreshToken = refreshTokenToUse
        });
        AccessToken = response?.AccessToken ?? throw new InvalidOperationException("AccessToken from response is null");
        RefreshToken = response?.RefreshToken ?? throw new InvalidOperationException("RefreshToken from response is null");
    }
}
