using IdentityModel;
using IdentityModel.Client;

using RestSharp;

namespace StravaSharp.OAuth2Client;

public abstract class OAuth2Client(OAuth2ClientConfiguration config)
{
<<<<<<< Updated upstream

||||||| Stash base
    private readonly OAuth2ClientConfiguration _config;

=======
>>>>>>> Stashed changes
    public string? AccessToken { get; protected set; }

    public string? RefreshToken { get; protected set; }

    public abstract string AuthorizeUri { get; }

    public abstract string TokenUri { get; }

    public OAuth2ClientConfiguration Configuration { get; } = config;

    public string GetAuthorizationUrl()
    {
        RestClient client = new();

<<<<<<< Updated upstream
        RestRequest request = new(new Uri(AuthorizeUri));
        request.AddParameter(OidcConstants.AuthorizeRequest.ClientId, Configuration.ClientId);
        request.AddParameter(OidcConstants.AuthorizeRequest.RedirectUri, Configuration.RedirectUri);
        request.AddParameter(OidcConstants.AuthorizeRequest.Scope, Configuration.Scope);
||||||| Stash base
        var request = new RestRequest(new Uri(AuthorizeUri));
        request.AddParameter(OidcConstants.AuthorizeRequest.ClientId, _config.ClientId);
        request.AddParameter(OidcConstants.AuthorizeRequest.RedirectUri, _config.RedirectUri);
        request.AddParameter(OidcConstants.AuthorizeRequest.Scope, _config.Scope);
=======
        RestRequest request = new RestRequest(new Uri(AuthorizeUri))
            .AddParameter(OidcConstants.AuthorizeRequest.ClientId, Configuration.ClientId)
            .AddParameter(OidcConstants.AuthorizeRequest.RedirectUri, Configuration.RedirectUri)
            .AddParameter(OidcConstants.AuthorizeRequest.Scope, Configuration.Scope);
>>>>>>> Stashed changes
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
        AccessToken = response?.AccessToken;
        RefreshToken = response?.RefreshToken;
    }
}
